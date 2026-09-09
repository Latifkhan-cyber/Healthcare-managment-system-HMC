# Payment Views
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings
from datetime import date

from ..models import (
    Appointment, QueueToken, PatientHistory,
    Payment, DoctorSchedule, Notification, DoctorReview, PaymentSettings
)
from ..forms import PaymentForm
from backend.apps.accounts.models import User

# Import shared helper
from .appointments import estimate_wait_time
from ..notification_service import create_notification


@login_required
def make_payment(request, appointment_id):
    """Patient, Receptionist, or Admin records/submits payment for an appointment."""
    if request.user.role in ('ADMIN', 'RECEPTIONIST'):
        appointment = get_object_or_404(Appointment, id=appointment_id)
    else:
        appointment = get_object_or_404(
            Appointment, id=appointment_id, patient=request.user
        )

    # Check if already paid
    existing_payment = getattr(appointment, 'payment', None)
    if existing_payment and existing_payment.status == 'PAID':
        messages.info(request, "This appointment has already been paid.")
        return redirect('clinic:payment_receipt', payment_id=existing_payment.id)

    # Ensure PaymentSettings exists
    payment_settings = PaymentSettings.objects.first()
    if not payment_settings:
        payment_settings = PaymentSettings.objects.create(
            jazzcash_number="0300-1234567",
            easypaisa_number="0311-7654321",
            bank_name="Meezan Bank Ltd",
            bank_account_title="Healthcare Medical Complex HMC",
            bank_account_number="PK45MEZN0009876543210101"
        )

    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES, instance=existing_payment)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.appointment = appointment
            
            method = form.cleaned_data.get('method', 'CASH')
            if not payment.amount:
                payment.amount = appointment.doctor.consultation_fee or 1500

            if request.user.role in ('ADMIN', 'RECEPTIONIST'):
                # Staff can immediately verify cash/digital payment
                payment.status = 'PAID'
                payment.save()
                appointment.status = 'CONFIRMED'
                appointment.save()

                # Generate Queue Token if checked in
                if not hasattr(appointment, 'queue_token'):
                    from .appointments import estimate_wait_time
                    existing_count = QueueToken.objects.filter(
                        appointment__doctor=appointment.doctor,
                        appointment__appointment_date=appointment.appointment_date,
                        is_active=True
                    ).count()
                    token_number = existing_count + 1
                    estimated_wait = estimate_wait_time(appointment.doctor, appointment.appointment_date)
                    QueueToken.objects.create(
                        appointment=appointment,
                        token_number=token_number,
                        estimated_wait_minutes=estimated_wait
                    )

                messages.success(request, f"Payment of PKR {payment.amount} confirmed for {appointment.patient.get_full_name()}!")
                return redirect('clinic:payment_receipt', payment_id=payment.id)
            else:
                # Patient digital submission or cash selection
                if method == 'CASH':
                    payment.status = 'PENDING'
                    payment.save()
                    appointment.save()
                    messages.success(request, "Cash on Arrival selected. Please pay at the clinic reception desk upon arrival.")
                else:
                    payment.status = 'PENDING'
                    payment.save()
                    appointment.save()
                    messages.success(request, "Payment proof submitted successfully! Your appointment will be confirmed by reception.")

                return redirect('clinic:my_appointments')
    else:
        initial = {
            'amount': appointment.doctor.consultation_fee or 1500,
            'method': existing_payment.method if existing_payment else 'JAZZCASH',
        }
        form = PaymentForm(instance=existing_payment, initial=initial)

    return render(request, 'clinic/make_payment.html', {
        'form': form,
        'appointment': appointment,
        'payment_settings': payment_settings,
        'existing_payment': existing_payment,
    })


@login_required
def payment_records(request):
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    payments = Payment.objects.select_related(
        'appointment__patient', 'appointment__doctor'
    ).order_by('-created_at')

    # Filter tab
    active_filter = request.GET.get('filter', 'all')
    if active_filter == 'online_pending':
        payments = payments.filter(status='PENDING').exclude(method='CASH')
    elif active_filter == 'cash_pending':
        payments = payments.filter(status='PENDING', method='CASH')
    elif active_filter == 'paid':
        payments = payments.filter(status='PAID')
    elif active_filter == 'failed':
        payments = payments.filter(status='FAILED')
    elif active_filter == 'refunded':
        payments = payments.filter(status='REFUNDED')

    # Search query
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        payments = payments.filter(
            Q(appointment__patient__username__icontains=q) |
            Q(appointment__patient__first_name__icontains=q) |
            Q(appointment__patient__last_name__icontains=q) |
            Q(appointment__patient__patient_id__icontains=q) |
            Q(appointment__patient__phone__icontains=q) |
            Q(transaction_id__icontains=q)
        )

    # Pagination
    from django.core.paginator import Paginator
    page = request.GET.get('page', 1)
    paginator = Paginator(payments, 20)
    payments_page = paginator.get_page(page)

    stats = {
        'total_revenue': Payment.objects.filter(status='PAID').aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'paid_count': Payment.objects.filter(status='PAID').count(),
        'pending_count': Payment.objects.filter(status='PENDING').count(),
        'pending_online_count': Payment.objects.filter(status='PENDING').exclude(method='CASH').count(),
        'pending_cash_count': Payment.objects.filter(status='PENDING', method='CASH').count(),
        'failed_count': Payment.objects.filter(status='FAILED').count(),
        'refunded_count': Payment.objects.filter(status='REFUNDED').count(),
        'active_filter': active_filter,
        'search_query': q,
    }

    return render(request, 'clinic/payment_records.html', {
        'payments': payments_page,
        'page_obj': payments_page,
        **stats,
    })


@login_required
def verify_payment(request, payment_id):
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id)
    # Mark payment as paid
    payment.status = 'PAID'
    payment.save()
    appointment = payment.appointment

    token_number = None
    if hasattr(appointment, 'queue_token') and appointment.queue_token and appointment.queue_token.is_active:
        token_number = appointment.queue_token.token_number
    elif appointment.appointment_date == date.today():
        existing_count = QueueToken.objects.filter(
            appointment__doctor=appointment.doctor,
            appointment__appointment_date=appointment.appointment_date,
            is_active=True
        ).count()
        token_number = existing_count + 1
        estimated_wait = estimate_wait_time(
            appointment.doctor, appointment.appointment_date
        )
        QueueToken.objects.create(
            appointment=appointment,
            token_number=token_number,
            estimated_wait_minutes=estimated_wait
        )

    # Confirm appointment
    if appointment.status != 'CONFIRMED':
        appointment.status = 'CONFIRMED'
        appointment.save()

    # Notify patient
    token_msg = f" Your queue token for today is #{token_number:02d}." if token_number else ""
    create_notification(
        recipient=appointment.patient,
        title="Online Payment Verified & Appointment Confirmed",
        message=f"Your online payment of PKR {payment.amount} ({payment.get_method_display()}) for Dr. {appointment.doctor.get_full_name()} on {appointment.appointment_date.strftime('%B %d, %Y')} at {appointment.time_slot} has been verified and confirmed.{token_msg}",
        notification_type='PAYMENT_VERIFIED',
    )

    messages.success(request, f"Online payment of PKR {payment.amount} verified successfully! Appointment confirmed for {appointment.patient.get_full_name()}.")
    next_url = request.GET.get('next') or request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and ('receptionist' in next_url or 'dashboard' in next_url or 'payment' in next_url):
        return redirect(next_url)
    return redirect('clinic:payment_records')


@login_required
def reject_payment(request, payment_id):
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id)
    payment.status = 'FAILED'
    payment.save()

    reason = request.POST.get('reason', 'Payment proof / transaction details could not be verified.')

    # Notify patient
    create_notification(
        recipient=payment.appointment.patient,
        title="Payment Verification Failed",
        message=f"Your payment proof for Dr. {payment.appointment.doctor.get_full_name()} was not verified. Reason: {reason}. Please re-submit payment proof or pay cash at reception.",
        notification_type='PAYMENT_RECEIVED',
    )

    messages.warning(request, f"Payment for {payment.appointment.patient.get_full_name()} has been rejected.")
    next_url = request.GET.get('next') or request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and ('receptionist' in next_url or 'dashboard' in next_url or 'payment' in next_url):
        return redirect(next_url)
    return redirect('clinic:payment_records')


@login_required
def payment_receipt(request, payment_id):
    """Generate a printable receipt or PDF for a payment."""
    payment = get_object_or_404(Payment, id=payment_id)

    # Access control: patient sees own, admin/receptionist sees all
    if request.user.role == 'PATIENT' and payment.appointment.patient != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.user.role == 'DOCTOR':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if payment.status != 'PAID':
        messages.error(request, "Receipt is only available for paid payments.")
        return redirect('clinic:payment_records')

    if payment.method == 'CASH':
        booking_type = 'Walk-in Booking'
        confirmation_note = 'Walk-in appointment confirmed instantly at reception by clinic staff.'
    else:
        booking_type = 'Online Appointment'
        confirmation_note = (
            'This online payment was verified by reception/admin, and the appointment is confirmed.'
            if payment.status == 'PAID'
            else 'This online payment requires admin verification to confirm the appointment.'
        )

    context = {
        'payment': payment,
        'appointment': payment.appointment,
        'patient': payment.appointment.patient,
        'doctor': payment.appointment.doctor,
        'payment_settings': PaymentSettings.objects.first(),
        'booking_type': booking_type,
        'confirmation_note': confirmation_note,
    }

    # If requested as raw pdf and weasyprint is available
    if request.GET.get('format') == 'pdf':
        try:
            from weasyprint import HTML
            html_string = render_to_string('clinic/receipt_pdf.html', context)
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            pdf_file = html.write_pdf()
            response = HttpResponse(pdf_file, content_type='application/pdf')
            filename = f"Healthcare_Receipt_{payment.id}_{payment.appointment.patient.patient_id or 'N/A'}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception:
            pass

    return render(request, 'clinic/receipt_pdf.html', context)


@login_required
def process_refund(request, payment_id):
    """Admin or Receptionist processes a refund for a paid payment."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    payment = get_object_or_404(Payment, id=payment_id, status='PAID')

    if request.method == 'POST':
        refund_amount = request.POST.get('refund_amount', '')
        refund_reason = request.POST.get('refund_reason', '')

        try:
            refund_amount = float(refund_amount)
        except (ValueError, TypeError):
            messages.error(request, "Invalid refund amount.")
            return redirect('clinic:process_refund', payment_id=payment.id)

        if refund_amount <= 0 or refund_amount > float(payment.amount):
            messages.error(request, f"Refund amount must be between 0 and {payment.amount}.")
            return redirect('clinic:process_refund', payment_id=payment.id)

        # Process the refund
        payment.status = 'REFUNDED'
        payment.notes = f"{payment.notes or ''}\n\nREFUND PROCESSED:\nAmount: PKR {refund_amount}\nReason: {refund_reason}\nDate: {date.today()}"
        payment.save()

        # Cancel the associated appointment
        appointment = payment.appointment
        appointment.status = 'CANCELLED'
        appointment.save()

        # Deactivate queue token if exists
        if hasattr(appointment, 'queue_token'):
            appointment.queue_token.is_active = False
            appointment.queue_token.save()

        messages.success(
            request,
            f"Refund of PKR {refund_amount} processed for {payment.appointment.patient.get_full_name()}. "
            f"Appointment cancelled."
        )
        return redirect('clinic:payment_records')

    return render(request, 'clinic/process_refund.html', {
        'payment': payment,
    })


@login_required
def patient_payment_history(request):
    """Patient views their own complete payment history."""
    if request.user.role != 'PATIENT':
        # Admin/receptionist redirect to records
        return redirect('clinic:payment_records')

    payments = Payment.objects.filter(
        appointment__patient=request.user
    ).select_related('appointment__doctor').order_by('-created_at')

    # Stats
    stats = {
        'total_payments': payments.count(),
        'total_paid': payments.filter(status='PAID').aggregate(s=Sum('amount'))['s'] or 0,
        'total_pending': payments.filter(status='PENDING').aggregate(s=Sum('amount'))['s'] or 0,
        'total_refunded': payments.filter(status='REFUNDED').aggregate(s=Sum('amount'))['s'] or 0,
    }

    return render(request, 'clinic/patient_payment_history.html', {
        'payments': payments,
        'stats': stats,
    })


@login_required
def confirm_cash_payment(request, payment_id):
    """Admin or Receptionist confirms cash payment received at clinic."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id, method='CASH', status='PENDING')
    payment.status = 'PAID'
    payment.save()
    appointment = payment.appointment

    token_number = None
    if hasattr(appointment, 'queue_token') and appointment.queue_token and appointment.queue_token.is_active:
        token_number = appointment.queue_token.token_number
    elif appointment.appointment_date == date.today():
        existing_count = QueueToken.objects.filter(
            appointment__doctor=appointment.doctor,
            appointment__appointment_date=appointment.appointment_date,
            is_active=True
        ).count()
        token_number = existing_count + 1
        estimated_wait = estimate_wait_time(
            appointment.doctor, appointment.appointment_date
        )
        QueueToken.objects.create(
            appointment=appointment,
            token_number=token_number,
            estimated_wait_minutes=estimated_wait
        )

    # Confirm appointment
    if appointment.status != 'CONFIRMED':
        appointment.status = 'CONFIRMED'
        appointment.save()

    # Notify patient
    token_msg = f" Your queue token is #{token_number:02d}." if token_number else ""
    create_notification(
        recipient=appointment.patient,
        title="Cash Payment Received & Confirmed",
        message=f"Your cash payment of PKR {payment.amount} for Dr. {appointment.doctor.get_full_name()} has been received and confirmed.{token_msg}",
        notification_type='PAYMENT_RECEIVED',
    )

    messages.success(request, f"Cash payment of PKR {payment.amount} confirmed for {appointment.patient.get_full_name()}.")
    next_url = request.GET.get('next') or request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and ('receptionist' in next_url or 'dashboard' in next_url or 'payment' in next_url):
        return redirect(next_url)
    return redirect('clinic:payment_records')


@login_required
def payment_settings(request):
    """Admin manages clinic payment account details."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    settings_obj, _ = PaymentSettings.objects.get_or_create(id=1)

    if request.method == 'POST':
        settings_obj.jazzcash_number = request.POST.get('jazzcash_number', '')
        settings_obj.easypaisa_number = request.POST.get('easypaisa_number', '')
        settings_obj.bank_name = request.POST.get('bank_name', '')
        settings_obj.bank_account_title = request.POST.get('bank_account_title', '')
        settings_obj.bank_account_number = request.POST.get('bank_account_number', '')
        settings_obj.save()
        messages.success(request, "Payment settings updated successfully!")
        return redirect('clinic:payment_settings')

    return render(request, 'clinic/payment_settings.html', {
        'settings': settings_obj,
    })