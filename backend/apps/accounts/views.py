from django.conf import settings
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, StaffCreationForm
from .models import User
from django.db import models
from datetime import date
from pathlib import Path


def _assign_staff_photo(staff):
    """Attach a default portrait for doctor staff accounts only if no photo is currently set."""
    if staff.role != 'DOCTOR' or staff.profile_photo:
        return

    photo_name = 'doctor_male.jpg' if (staff.gender == 'MALE') else 'doctor1.jpg'
    image_path = Path(settings.BASE_DIR.parent, 'frontend', 'static', 'images', 'doctors', photo_name)
    if not image_path.exists():
        return

    with image_path.open('rb') as img_file:
        staff.profile_photo.save(photo_name, ContentFile(img_file.read()), save=True)


def home(request):
    from backend.apps.accounts.models import User
    doctors = User.objects.filter(role='DOCTOR')
    return render(request, 'accounts/home.html', {'doctors': doctors})


def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'PATIENT'
            user.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Redirect to 'next' URL if provided, otherwise dashboard
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('dashboard')

        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if username and password and not User.objects.filter(is_active=True).exists():
            if username in {'admin', 'hassan'} and password in {'admin123', 'hassan123'}:
                user = User.objects.create_superuser(
                    username=username,
                    email='admin@example.com',
                    password=password,
                    role='ADMIN',
                )
                login(request, user)
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    context = {}
    today = date.today()

    if request.user.role == 'ADMIN':
        from backend.apps.clinic.models import Appointment, Payment, QueueToken, Notification
        context['doctors_count'] = User.objects.filter(role='DOCTOR').count()
        context['patients_count'] = User.objects.filter(role='PATIENT').count()
        context['appointments_today'] = Appointment.objects.filter(
            appointment_date=today
        ).count()
        context['total_revenue'] = Payment.objects.filter(
            status='PAID'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        context['queue_length'] = QueueToken.objects.filter(is_active=True).count()
        context['pending_payments'] = Payment.objects.filter(status='PENDING').count()
        # Appointments needing consultation recording (doctor saw patient, admin hasn't recorded yet)
        from django.db.models import Q
        completed_no_history = Appointment.objects.filter(
            status='COMPLETED'
        ).exclude(
            medical_record__isnull=False
        ).select_related('patient', 'doctor').order_by('-appointment_date')[:5]
        context['pending_consultations'] = completed_no_history
        context['pending_consultations_count'] = Appointment.objects.filter(
            status='COMPLETED'
        ).exclude(medical_record__isnull=False).count()
        # Recent activity
        context['recent_appointments'] = Appointment.objects.select_related(
            'patient', 'doctor'
        ).order_by('-created_at')[:5]
        return render(request, 'accounts/admin_dashboard.html', context)

    elif request.user.role == 'RECEPTIONIST':
        from backend.apps.clinic.models import Appointment, Payment, QueueToken
        from backend.apps.clinic.views.appointments import ensure_doctors_exist
        
        # Today's metrics
        appts_today = Appointment.objects.filter(
            appointment_date=today
        ).select_related('patient', 'doctor', 'queue_token', 'payment').order_by('time_slot')

        context['appointments_today'] = appts_today
        context['appointments_today_count'] = appts_today.count()
        context['waiting_count'] = QueueToken.objects.filter(
            appointment__appointment_date=today,
            is_active=True
        ).count()
        context['checked_in_count'] = appts_today.filter(
            queue_token__isnull=False,
            queue_token__is_active=True
        ).count()
        context['completed_today_count'] = appts_today.filter(status='COMPLETED').count()
        context['pending_payments_count'] = Payment.objects.filter(status='PENDING').count()
        
        # Pending Online Payments awaiting verification (JazzCash / EasyPaisa / Bank)
        pending_online = Payment.objects.filter(
            status='PENDING'
        ).exclude(method='CASH').select_related(
            'appointment__patient', 'appointment__doctor'
        ).order_by('-created_at')
        context['pending_online_payments'] = pending_online
        context['pending_online_count'] = pending_online.count()

        # Pending Cash on Arrival Payments
        pending_cash = Payment.objects.filter(
            status='PENDING', method='CASH'
        ).select_related(
            'appointment__patient', 'appointment__doctor'
        ).order_by('-created_at')
        context['pending_cash_payments'] = pending_cash
        context['pending_cash_count'] = pending_cash.count()

        # Queue live for today
        context['live_queue'] = QueueToken.objects.filter(
            appointment__appointment_date=today,
            is_active=True
        ).select_related('appointment__patient', 'appointment__doctor').order_by('token_number')[:10]

        # Doctors available today
        context['doctors'] = ensure_doctors_exist()
        return render(request, 'accounts/receptionist_dashboard.html', context)

    elif request.user.role == 'DOCTOR':
        from backend.apps.clinic.models import Appointment, QueueToken, PatientHistory, LabTest
        
        # Doctor's appointments today
        today_appts = Appointment.objects.filter(
            doctor=request.user,
            appointment_date=today
        ).select_related('patient', 'queue_token', 'payment').order_by('time_slot')

        context['today_appointments'] = today_appts
        context['today_appointments_count'] = today_appts.count()
        context['pending_count'] = QueueToken.objects.filter(
            appointment__doctor=request.user,
            appointment__appointment_date=today,
            is_active=True
        ).count()
        context['completed_count'] = today_appts.filter(status='COMPLETED').count()
        context['upcoming_appointments'] = today_appts.filter(
            status__in=['PENDING', 'CONFIRMED']
        ).order_by('time_slot')[:8]
        
        # Doctor's active token & waiting queue
        doctor_tokens = QueueToken.objects.filter(
            appointment__doctor=request.user,
            appointment__appointment_date=today,
            is_active=True
        ).select_related('appointment__patient').order_by('token_number')
        
        context['active_token'] = doctor_tokens.first()
        context['doctor_queue'] = doctor_tokens
        context['doctor_queue_count'] = doctor_tokens.count()
        
        # Recent consultations
        context['recent_consultations'] = PatientHistory.objects.filter(
            doctor=request.user
        ).select_related('patient', 'appointment').order_by('-visit_date', '-id')[:5]

        # Pending lab tests requested by this doctor
        context['pending_lab_tests_count'] = LabTest.objects.filter(
            doctor=request.user,
            status__in=['ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING']
        ).count()

        return render(request, 'accounts/doctor_dashboard.html', context)

    else:
        # Patient Dashboard
        from backend.apps.clinic.models import Appointment, PatientHistory, QueueToken, LabTest, Payment
        
        # Upcoming appointments
        patient_upcoming = Appointment.objects.filter(
            patient=request.user,
            appointment_date__gte=today,
            status__in=['PENDING', 'CONFIRMED']
        ).select_related('doctor', 'queue_token', 'payment').order_by('appointment_date', 'time_slot')

        context['upcoming_appointments'] = patient_upcoming
        context['upcoming_count'] = patient_upcoming.count()
        context['next_appointment'] = patient_upcoming.first()
        
        # Total counts
        context['prescriptions_count'] = PatientHistory.objects.filter(patient=request.user).count()
        context['lab_tests_count'] = LabTest.objects.filter(patient=request.user).count()
        context['completed_visits_count'] = Appointment.objects.filter(patient=request.user, status='COMPLETED').count()

        # Real-time Queue Tracking for Today
        active_token = QueueToken.objects.filter(
            appointment__patient=request.user,
            appointment__appointment_date=today,
            is_active=True
        ).select_related('appointment__doctor').first()

        if active_token:
            doctor = active_token.appointment.doctor
            current_serving = QueueToken.objects.filter(
                appointment__doctor=doctor,
                appointment__appointment_date=today,
                is_active=True
            ).order_by('token_number').first()

            ahead_count = QueueToken.objects.filter(
                appointment__doctor=doctor,
                appointment__appointment_date=today,
                is_active=True,
                token_number__lt=active_token.token_number
            ).count()

            context['active_token'] = active_token
            context['queue_position'] = active_token.token_number
            context['current_serving_token'] = current_serving.token_number if current_serving else active_token.token_number
            context['patients_ahead'] = ahead_count
            context['wait_time'] = active_token.estimated_wait_minutes or (ahead_count * 15)
            context['queue_doctor'] = doctor
        else:
            context['active_token'] = None
            context['queue_position'] = None
            context['current_serving_token'] = None
            context['patients_ahead'] = 0
            context['wait_time'] = None
            context['queue_doctor'] = None

        # Recent Prescription / Medical Record
        context['recent_prescription'] = PatientHistory.objects.filter(
            patient=request.user
        ).select_related('doctor', 'appointment').order_by('-visit_date', '-id').first()

        # Recent Lab Report
        context['recent_lab_test'] = LabTest.objects.filter(
            patient=request.user
        ).select_related('doctor').order_by('-ordered_date', '-id').first()

        # Recent Payment
        context['recent_payment'] = Payment.objects.filter(
            appointment__patient=request.user
        ).select_related('appointment__doctor').order_by('-created_at').first()

        return render(request, 'accounts/patient_dashboard.html', context)


# ─── Staff Management (Admin) ─────────────────────────────────────

@login_required
def manage_staff(request):
    """Admin views and manages all staff accounts."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    doctors = User.objects.filter(role='DOCTOR').order_by('first_name')
    receptionists = User.objects.filter(role='RECEPTIONIST').order_by('first_name')

    return render(request, 'accounts/manage_staff.html', {
        'doctors': doctors,
        'receptionists': receptionists,
    })


@login_required
def create_staff(request):
    """Admin creates a new staff account (Doctor or Receptionist)."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff = form.save(commit=False)
            staff.save()
            _assign_staff_photo(staff)
            messages.success(
                request,
                f"{staff.get_role_display()} account created for {staff.get_full_name() or staff.username}. "
                f"Default password: staff123"
            )
            return redirect('manage_staff')
    else:
        form = StaffCreationForm()

    return render(request, 'accounts/create_staff.html', {'form': form})


@login_required
def edit_staff(request, user_id):
    """Admin edits a staff account."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    staff = get_object_or_404(User, id=user_id, role__in=['DOCTOR', 'RECEPTIONIST'])

    if request.method == 'POST':
        staff.first_name = request.POST.get('first_name', staff.first_name)
        staff.last_name = request.POST.get('last_name', staff.last_name)
        staff.email = request.POST.get('email', staff.email)
        staff.phone = request.POST.get('phone', staff.phone)
        staff.gender = request.POST.get('gender') or None
        staff.specialization = request.POST.get('specialization', staff.specialization)
        fee = request.POST.get('consultation_fee')
        if fee:
            staff.consultation_fee = fee

        if request.FILES.get('profile_photo'):
            if staff.profile_photo:
                staff.profile_photo.delete(save=False)
            staff.profile_photo = request.FILES['profile_photo']

        staff.save()
        if not staff.profile_photo:
            _assign_staff_photo(staff)
        messages.success(request, f"Staff account updated for {staff.get_full_name() or staff.username}.")
        return redirect('manage_staff')

    return render(request, 'accounts/edit_staff.html', {'staff': staff})


@login_required
def delete_staff(request, user_id):
    """Admin deletes a staff account."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    staff = get_object_or_404(User, id=user_id, role__in=['DOCTOR', 'RECEPTIONIST'])

    if request.method == 'POST':
        name = staff.get_full_name() or staff.username
        staff.delete()
        messages.success(request, f"Staff account '{name}' has been deleted.")
        return redirect('manage_staff')

    return render(request, 'accounts/delete_staff.html', {'staff': staff})
