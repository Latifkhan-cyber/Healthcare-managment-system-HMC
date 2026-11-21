from django.core.management.base import BaseCommand
from backend.apps.accounts.models import User


class Command(BaseCommand):
    help = 'Reset all passwords to their defaults'

    def handle(self, *args, **options):
        self.stdout.write('Resetting all passwords to defaults...')
        self.stdout.write('')
        
        # Reset admin passwords
        for username in ['admin', 'hassan']:
            try:
                user = User.objects.get(username=username)
                password = f'{username}123'
                user.set_password(password)
                user.save()
                self.stdout.write(f'✓ Admin: {username} / {password}')
            except User.DoesNotExist:
                pass
        
        # Reset receptionist passwords
        for username in ['receptionist', 'reception']:
            try:
                user = User.objects.get(username=username)
                user.set_password('recep123')
                user.save()
                self.stdout.write(f'✓ Receptionist: {username} / recep123')
            except User.DoesNotExist:
                pass
        
        # Reset doctor passwords
        doctors = User.objects.filter(role='DOCTOR')
        for doctor in doctors:
            doctor.set_password('doctor123')
            doctor.save()
            self.stdout.write(f'✓ Doctor: {doctor.username} / doctor123')
        
        # Reset patient passwords
        patients = User.objects.filter(role='PATIENT')
        for patient in patients:
            patient.set_password('patient123')
            patient.save()
            self.stdout.write(f'✓ Patient: {patient.username} / patient123')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('✅ ALL PASSWORDS HAVE BEEN RESET!'))
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write('')
        self.stdout.write('LOGIN CREDENTIALS:')
        self.stdout.write('  Admins:        admin/admin123')
        self.stdout.write('  Receptionists: receptionist/recep123, reception/recep123')
        self.stdout.write('  Doctors:       [username]/doctor123')
        self.stdout.write('  Patients:      [username]/patient123')
