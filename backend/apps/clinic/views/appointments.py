# Appointments Views
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from datetime import date, timedelta, datetime
from django.http import JsonResponse
from django.core.files.base import ContentFile
from pathlib import Path

from ..models import Appointment, QueueToken, Payment, DoctorSchedule
from ..forms import AppointmentForm
from backend.apps.accounts.models import User
from ..notification_service import create_notification


def _assign_doctor_photo(doctor, photo_name):
    """Attach a bundled doctor image to a doctor account only if no photo is set."""
    if doctor.profile_photo:
        return

    image_path = Path(settings.BASE_DIR.parent, 'frontend', 'static', 'images', 'doctors', photo_name)
    if not image_path.exists():
        return

    with image_path.open('rb') as img_file:
        doctor.profile_photo.save(photo_name, ContentFile(img_file.read()), save=True)


def ensure_doctors_exist():
    """Ensure a complete roster of doctor accounts is available for booking forms and admin flows."""
    doctor_specs = [
        {'username': 'dr_hira', 'first_name': 'Hira', 'last_name': 'Sheheryar', 'specialization': 'Gynecology', 'consultation_fee': 1500, 'bio': 'Specializes in women’s health, prenatal care, and minimally invasive gynecological treatments.', 'photo': 'doctor1.jpg', 'gender': 'FEMALE'},
        {'username': 'dr_saba', 'first_name': 'Saba', 'last_name': 'Gul', 'specialization': 'Pediatrics', 'consultation_fee': 1200, 'bio': 'Experienced pediatrician focused on child wellness, vaccinations, and routine growth monitoring.', 'photo': 'doctor_male.jpg', 'gender': 'MALE'},
        {'username': 'dr_taj', 'first_name': 'Taj', 'last_name': 'Bahadur', 'specialization': 'Cardiology', 'consultation_fee': 1800, 'bio': 'Cardiologist with expertise in heart disease screening, hypertension, and preventive cardiac care.', 'photo': 'doctor_male.jpg', 'gender': 'MALE'},
        {'username': 'dr_idrees', 'first_name': 'Idrees', 'last_name': 'Khan', 'specialization': 'General Medicine', 'consultation_fee': 1000, 'bio': 'General medicine physician offering diagnosis, chronic disease management, and family care.', 'photo': 'doctor_male.jpg', 'gender': 'MALE'},
        {'username': 'dr_ahmed', 'first_name': 'Ahmed', 'last_name': 'Raza', 'specialization': 'Orthopedics', 'consultation_fee': 1400, 'bio': 'Orthopedic specialist focused on bone, joint, and sports injury care.', 'photo': 'doctor_male.jpg', 'gender': 'MALE'},
    ]

    for spec in doctor_specs:
        doctor, created = User.objects.get_or_create(
            username=spec['username'],
            defaults={
                'first_name': spec['first_name'],
                'last_name': spec['last_name'],
                'email': f"{spec['username']}@clinic.com",
                'role': 'DOCTOR',
                'specialization': spec['specialization'],
                'consultation_fee': spec['consultation_fee'],
                'address': f"{spec['specialization']} Clinic, Main Hospital Lane",
                'gender': spec.get('gender'),
            }
        )

        if not created:
            doctor.first_name = spec['first_name']
            doctor.last_name = spec['last_name']
            doctor.email = f"{spec['username']}@clinic.com"
            doctor.role = 'DOCTOR'
            doctor.specialization = spec['specialization']
            doctor.consultation_fee = spec['consultation_fee']
            doctor.address = f"{spec['specialization']} Clinic, Main Hospital Lane"
            doctor.gender = spec.get('gender') or doctor.gender
            doctor.save(update_fields=['first_name', 'last_name', 'email', 'role', 'specialization', 'consultation_fee', 'address', 'gender'])

        if not doctor.has_usable_password() or doctor.username in {'dr_hira', 'dr_saba', 'dr_taj', 'dr_idrees', 'dr_ahmed'}:
            doctor.set_password('doctor123')
            doctor.save(update_fields=['password'])
        _assign_doctor_photo(doctor, spec.get('photo', 'doctor1.jpg'))

        # Ensure weekly schedule (Mon-Sat 9am-5pm) exists
        for day in range(6):  # Monday=0 to Saturday=5
            DoctorSchedule.objects.get_or_create(
                doctor=doctor,
                day_of_week=day,
                defaults={
                    'start_time': '09:00:00',
                    'end_time': '17:00:00',
                    'is_available': True
                }
            )

    return User.objects.filter(role='DOCTOR').order_by('id')


def estimate_wait_time(doctor, appointment_date):
    """
    Estimate wait time for a patient based on active queue length for this doctor today.
    Can be enhanced with actual timing data later.
    """
    avg_time = 15  # minutes per patient
    patients_ahead = QueueToken.objects.filter(
        appointment__doctor=doctor,
        appointment__appointment_date=appointment_date,
        is_active=True
    ).count()
    return patients_ahead * avg_time


@login_required
def book_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = request.user
            appointment.save()
            messages.success(
                request,
                "Appointment booked successfully! Please proceed to payment."
            )
            return redirect('clinic:make_payment', appointment_id=appointment.id)
    else:
        form = AppointmentForm()

    doctors = ensure_doctors_exist().order_by('first_name')
    specializations = list(doctors
                          .exclude(specialization__isnull=True)
                          .exclude(specialization='')
                          .values_list('specialization', flat=True)
                          .distinct().order_by('specialization'))

    preselected_doctor_id = request.GET.get('doctor_id', '')

    return render(request, 'clinic/book_appointment.html', {
        'form': form,
        'doctors': doctors,
        'specializations': specializations,
        'today': date.today(),
        'preselected_doctor_id': preselected_doctor_id,
    })


@login_required
def my_appointments(request):
    today = date.today()
    
    if request.user.role == 'DOCTOR':
        appointments = Appointment.objects.filter(
            doctor=request.user
        ).select_related('patient', 'queue_token', 'payment').order_by('-appointment_date', 'time_slot')
    elif request.user.role in ('ADMIN', 'RECEPTIONIST'):
        appointments = Appointment.objects.all().select_related('patient', 'doctor', 'queue_token', 'payment').order_by('-appointment_date', 'time_slot')
    else:
        appointments = Appointment.objects.filter(
            patient=request.user
        ).select_related('doctor', 'queue_token', 'payment').order_by('-appointment_date', 'time_slot')

    stats = {
        'total': appointments.count(),
        'completed': appointments.filter(status='COMPLETED').count(),
        'upcoming': appointments.filter(
            status='CONFIRMED', appointment_date__gte=today
        ).count(),
        'pending': appointments.filter(status='PENDING').count(),
        'today': appointments.filter(appointment_date=today).count(),
    }

    return render(request, 'clinic/my_appointments.html', {
        'appointments': appointments,
        'stats': stats,
        'today': today,
    })


@login_required
def get_doctor_slots(request):
    """AJAX endpoint: returns available 30-min time slots for a doctor on a given date."""
    doctor_id = request.GET.get('doctor_id')
    date_str = request.GET.get('date')

    if not doctor_id or not date_str:
        return JsonResponse({'error': 'Missing doctor_id or date'}, status=400)

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    day_of_week = selected_date.weekday()

    # Get doctor's schedule for this day
    schedules = DoctorSchedule.objects.filter(
        doctor_id=doctor_id,
        day_of_week=day_of_week,
        is_available=True
    )

    # Generate 30-min slots
    slots = []
    if schedules.exists():
        for sched in schedules:
            current = datetime.combine(selected_date, sched.start_time)
            end = datetime.combine(selected_date, sched.end_time)
            while current < end:
                time_str = current.strftime('%H:%M')
                is_booked = Appointment.objects.filter(
                    doctor_id=doctor_id,
                    appointment_date=selected_date,
                    time_slot=time_str,
                    status__in=['PENDING', 'CONFIRMED']
                ).exists()
                slots.append({
                    'time': time_str,
                    'display': current.strftime('%I:%M %p'),
                    'available': not is_booked
                })
                current += timedelta(minutes=30)
    else:
        # Default 09:00 AM - 05:00 PM standard clinic slots
        from datetime import time as dt_time
        start_t = dt_time(9, 0)
        end_t = dt_time(17, 0)
        current = datetime.combine(selected_date, start_t)
        end = datetime.combine(selected_date, end_t)
        while current < end:
            time_str = current.strftime('%H:%M')
            is_booked = Appointment.objects.filter(
                doctor_id=doctor_id,
                appointment_date=selected_date,
                time_slot=time_str,
                status__in=['PENDING', 'CONFIRMED']
            ).exists()
            slots.append({
                'time': time_str,
                'display': current.strftime('%I:%M %p'),
                'available': not is_booked
            })
            current += timedelta(minutes=30)

    return JsonResponse({'slots': slots})


@login_required
def cancel_appointment(request, appointment_id):
    if request.user.role in ('ADMIN', 'RECEPTIONIST'):
        appointment = get_object_or_404(Appointment, id=appointment_id)
    else:
        appointment = get_object_or_404(
            Appointment, id=appointment_id, patient=request.user
        )
    if request.method == 'POST':
        if appointment.status in ('PENDING', 'CONFIRMED'):
            appointment.status = 'CANCELLED'
            appointment.save()
            if hasattr(appointment, 'queue_token'):
                appointment.queue_token.is_active = False
                appointment.queue_token.save()
            messages.success(request, "Appointment cancelled.")
        else:
            messages.error(request, "This appointment cannot be cancelled.")
        if request.user.role in ('ADMIN', 'RECEPTIONIST'):
            return redirect('dashboard')
        return redirect('clinic:my_appointments')
    return render(request, 'clinic/cancel_appointment.html', {
        'appointment': appointment
    })


@login_required
def appointment_detail(request, appointment_id):
    """View full details of a specific appointment."""
    appointment = get_object_or_404(
        Appointment, id=appointment_id
    )

    # Role-based access: patient sees own, doctor sees own, admin/receptionist sees all
    if request.user.role == 'PATIENT' and appointment.patient != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.user.role == 'DOCTOR' and appointment.doctor != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    # Get related data
    token = getattr(appointment, 'queue_token', None)
    payment = getattr(appointment, 'payment', None)
    medical_record = getattr(appointment, 'medical_record', None)
    review = getattr(appointment, 'review', None)

    return render(request, 'clinic/appointment_detail.html', {
        'appointment': appointment,
        'token': token,
        'payment': payment,
        'medical_record': medical_record,
        'review': review,
    })


@login_required
def confirm_appointment(request, appointment_id):
    """Admin/receptionist confirms a pending appointment and creates a queue token."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    appointment = get_object_or_404(Appointment, id=appointment_id)

    # Only pending appointments should be confirmed here
    if appointment.status == 'CONFIRMED':
        messages.info(request, "Appointment already confirmed.")
        return redirect('dashboard')

    # Change status and create queue token if needed
    appointment.status = 'CONFIRMED'
    appointment.save()

    token_number = None
    if not hasattr(appointment, 'queue_token') or not appointment.queue_token.is_active:
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

    # Notify patient
    msg = f"Your appointment with Dr. {appointment.doctor.get_full_name()} on {appointment.appointment_date.strftime('%B %d, %Y')} at {appointment.time_slot} has been confirmed."
    if token_number:
        msg += f" Queue token: #{token_number}."

    create_notification(
        recipient=appointment.patient,
        title="Appointment Confirmed",
        message=msg,
        notification_type='APPOINTMENT_CONFIRMED',
    )

    messages.success(request, "Appointment confirmed.")
    return redirect('dashboard')


@login_required
def reject_appointment(request, appointment_id):
    """Admin/receptionist rejects/cancels an appointment and notifies the patient."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    appointment = get_object_or_404(Appointment, id=appointment_id)

    # If already cancelled or completed, inform user
    if appointment.status in ('CANCELLED', 'COMPLETED'):
        messages.info(request, "This appointment cannot be rejected.")
        return redirect('dashboard')

    appointment.status = 'CANCELLED'
    appointment.save()

    # Deactivate any existing queue token
    if hasattr(appointment, 'queue_token'):
        appointment.queue_token.is_active = False
        appointment.queue_token.save()

    create_notification(
        recipient=appointment.patient,
        title="Appointment Cancelled",
        message=f"Your appointment with Dr. {appointment.doctor.get_full_name()} on {appointment.appointment_date.strftime('%B %d, %Y')} has been cancelled by the clinic.",
        notification_type='APPOINTMENT_CANCELLED',
    )

    messages.success(request, "Appointment rejected and patient notified.")
    return redirect('dashboard')


@login_required
def reschedule_appointment(request, appointment_id):
    """Patient, Receptionist, or Admin reschedules appointment to a new date/time."""
    if request.user.role in ('ADMIN', 'RECEPTIONIST'):
        appointment = get_object_or_404(Appointment, id=appointment_id)
    else:
        appointment = get_object_or_404(
            Appointment, id=appointment_id, patient=request.user
        )

    # Can only reschedule PENDING or CONFIRMED appointments
    if appointment.status not in ('PENDING', 'CONFIRMED'):
        messages.error(request, "This appointment cannot be rescheduled.")
        if request.user.role in ('ADMIN', 'RECEPTIONIST'):
            return redirect('dashboard')
        return redirect('clinic:my_appointments')

    if request.method == 'POST':
        new_date = request.POST.get('appointment_date')
        new_time = request.POST.get('time_slot')

        if not new_date or not new_time:
            messages.error(request, "Please select both date and time.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        from datetime import date as date_type
        from datetime import datetime

        try:
            parsed_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        if parsed_date < date_type.today():
            messages.error(request, "Cannot reschedule to a past date.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        # Check for conflicts (exclude current appointment)
        from django.db.models import Q
        conflict = Appointment.objects.filter(
            doctor=appointment.doctor,
            appointment_date=parsed_date,
            time_slot=new_time
        ).exclude(id=appointment.id).exists()

        if conflict:
            messages.error(
                request,
                "This time slot is already booked for the selected doctor. Please choose another."
            )
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        # Update appointment
        appointment.appointment_date = parsed_date
        appointment.time_slot = new_time
        appointment.reason = request.POST.get('reason', appointment.reason)
        appointment.save()

        if request.user.role in ('ADMIN', 'RECEPTIONIST'):
            return redirect('dashboard')
        return redirect('clinic:my_appointments')

    return render(request, 'clinic/reschedule_appointment.html', {
        'appointment': appointment,
        'today': date.today(),
    })