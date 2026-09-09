# Doctor Views
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg

from ..models import DoctorSchedule, DoctorReview, Appointment
from ..forms import DoctorScheduleForm, DoctorReviewForm
from backend.apps.accounts.models import User


@login_required
def manage_doctors(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')
    doctors = User.objects.filter(role='DOCTOR')
    return render(request, 'clinic/manage_doctors.html', {
        'doctors': doctors,
    })


@login_required
def doctor_schedule(request, doctor_id):
    if request.user.role not in ('ADMIN', 'DOCTOR'):
        return redirect('dashboard')
    
    # Doctor can only manage their own schedule unless admin
    if request.user.role == 'DOCTOR' and request.user.id != doctor_id:
        messages.error(request, "Access denied.")
        return redirect('clinic:doctor_my_profile')

    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    schedules = DoctorSchedule.objects.filter(doctor=doctor).order_by('day_of_week')

    if request.method == 'POST':
        day_of_week = request.POST.get('day_of_week')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        is_available = request.POST.get('is_available') == 'on' or request.POST.get('is_available') == 'true'

        if day_of_week and start_time and end_time:
            DoctorSchedule.objects.update_or_create(
                doctor=doctor,
                day_of_week=int(day_of_week),
                defaults={
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_available': is_available
                }
            )
            messages.success(request, "Schedule updated successfully.")
            if request.user.role == 'DOCTOR':
                return redirect('clinic:doctor_my_profile')
            return redirect('clinic:doctor_schedule', doctor_id=doctor.id)
        else:
            form = DoctorScheduleForm(request.POST)
            if form.is_valid():
                sched = form.save(commit=False)
                sched.doctor = doctor
                sched.save()
                messages.success(request, "Schedule updated.")
                if request.user.role == 'DOCTOR':
                    return redirect('clinic:doctor_my_profile')
                return redirect('clinic:doctor_schedule', doctor_id=doctor.id)
    else:
        form = DoctorScheduleForm()

    return render(request, 'clinic/doctor_schedule.html', {
        'doctor': doctor,
        'schedules': schedules,
        'form': form,
    })


@login_required
def doctor_my_profile(request):
    """Doctor views and edits their own profile information and manages weekly availability."""
    if request.user.role != 'DOCTOR':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    doctor = request.user
    schedules = DoctorSchedule.objects.filter(doctor=doctor).order_by('day_of_week')
    reviews = DoctorReview.objects.filter(doctor=doctor).select_related('patient').order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            doctor.first_name = request.POST.get('first_name', doctor.first_name).strip()
            doctor.last_name = request.POST.get('last_name', doctor.last_name).strip()
            doctor.phone = request.POST.get('phone', doctor.phone).strip()
            doctor.email = request.POST.get('email', doctor.email).strip()

            # Profile photo
            if 'profile_photo' in request.FILES:
                doctor.profile_photo = request.FILES['profile_photo']

            doctor.save()
            messages.success(request, "Profile information updated successfully.")
            return redirect('clinic:doctor_my_profile')

        elif action == 'update_schedule':
            day_of_week = request.POST.get('day_of_week')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            is_available = 'is_available' in request.POST

            if day_of_week and start_time and end_time:
                DoctorSchedule.objects.update_or_create(
                    doctor=doctor,
                    day_of_week=int(day_of_week),
                    defaults={
                        'start_time': start_time,
                        'end_time': end_time,
                        'is_available': is_available
                    }
                )
                messages.success(request, "Working hours / schedule updated.")
            return redirect('clinic:doctor_my_profile')

    return render(request, 'clinic/doctor_my_profile.html', {
        'doctor': doctor,
        'schedules': schedules,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'day_choices': DoctorSchedule.DAY_CHOICES,
    })


@login_required
def review_doctor(request, appointment_id):
    if request.user.role != 'PATIENT':
        return redirect('dashboard')
    appointment = get_object_or_404(
        Appointment, id=appointment_id, patient=request.user, status='COMPLETED'
    )
    if hasattr(appointment, 'review'):
        messages.info(request, "You have already reviewed this appointment.")
        return redirect('clinic:my_appointments')

    if request.method == 'POST':
        form = DoctorReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.patient = request.user
            review.doctor = appointment.doctor
            review.appointment = appointment
            review.save()
            messages.success(request, "Thank you for your review!")
            return redirect('clinic:my_appointments')
    else:
        form = DoctorReviewForm()

    return render(request, 'clinic/review_doctor.html', {
        'form': form,
        'appointment': appointment,
    })


@login_required
def doctor_reviews(request, doctor_id):
    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    reviews = DoctorReview.objects.filter(
        doctor=doctor
    ).select_related('patient').order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    return render(request, 'clinic/doctor_reviews.html', {
        'doctor': doctor,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })


def doctor_profile(request, doctor_id):
    """Public-facing doctor profile with reviews and schedule."""
    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    reviews = DoctorReview.objects.filter(
        doctor=doctor
    ).select_related('patient').order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    return render(request, 'clinic/doctor_profile.html', {
        'doctor': doctor,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })


def public_doctor_search(request):
    """Public and patient doctor directory with search, specialization filter, and schedule availability."""
    from django.db.models import Q
    query = request.GET.get('q', '').strip()
    specialty_filter = request.GET.get('specialty', '').strip()

    doctors_qs = User.objects.filter(role='DOCTOR').order_by('first_name')

    if query:
        doctors_qs = doctors_qs.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(specialization__icontains=query)
        )

    if specialty_filter:
        doctors_qs = doctors_qs.filter(specialization__icontains=specialty_filter)

    # Collect available specialties
    specialties = list(User.objects.filter(role='DOCTOR').exclude(specialization='').values_list('specialization', flat=True).distinct())

    doctors_data = []
    for d in doctors_qs:
        reviews = DoctorReview.objects.filter(doctor=d)
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        schedules = DoctorSchedule.objects.filter(doctor=d, is_available=True).order_by('day_of_week')
        doctors_data.append({
            'doctor': d,
            'avg_rating': avg_rating,
            'review_count': reviews.count(),
            'schedules': schedules,
        })

    return render(request, 'clinic/doctor_search.html', {
        'doctors': doctors_data,
        'specialties': specialties,
        'query': query,
        'selected_specialty': specialty_filter,
    })