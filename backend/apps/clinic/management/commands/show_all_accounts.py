from django.core.management.base import BaseCommand
from backend.apps.accounts.models import User


class Command(BaseCommand):
    help = 'Display all user accounts with their details'

    def handle(self, *args, **options):
        users = User.objects.all().order_by('role', 'username')
        
        self.stdout.write('='*80)
        self.stdout.write('ALL USER ACCOUNTS IN THE SYSTEM')
        self.stdout.write('='*80)
        self.stdout.write('')
        
        # Group by role
        roles = ['ADMIN', 'RECEPTIONIST', 'DOCTOR', 'PATIENT']
        
        for role in roles:
            role_users = users.filter(role=role)
            if role_users.exists():
                self.stdout.write(self.style.SUCCESS(f'\n{role}S:'))
                self.stdout.write('-'*80)
                
                for user in role_users:
                    self.stdout.write(f'  ID: {user.id}')
                    self.stdout.write(f'  Username: {user.username}')
                    self.stdout.write(f'  Name: {user.first_name} {user.last_name}')
                    if user.email:
                        self.stdout.write(f'  Email: {user.email}')
                    if user.phone:
                        self.stdout.write(f'  Phone: {user.phone}')
                    if role == 'PATIENT' and user.patient_id:
                        self.stdout.write(f'  Patient ID: {user.patient_id}')
                    if role == 'DOCTOR' and user.specialization:
                        self.stdout.write(f'  Specialization: {user.specialization}')
                        self.stdout.write(f'  Consultation Fee: Rs. {user.consultation_fee}')
                    
                    # Note: Passwords are hashed, but we know the defaults from seed data
                    if role == 'ADMIN':
                        if user.username in ['hassan', 'admin']:
                            password = f'{user.username}123'
                            self.stdout.write(f'  Password: {password}')
                    elif role == 'DOCTOR':
                        self.stdout.write(f'  Password: doctor123')
                    elif role == 'PATIENT':
                        self.stdout.write(f'  Password: patient123')
                    elif role == 'RECEPTIONIST':
                        self.stdout.write(f'  Password: recep123')
                    
                    self.stdout.write('')
        
        self.stdout.write('='*80)
        self.stdout.write(f'TOTAL USERS: {users.count()}')
        self.stdout.write('='*80)
        self.stdout.write('')
        self.stdout.write('QUICK REFERENCE:')
        self.stdout.write('  Admins:         hassan/hassan123, admin/admin123')
        self.stdout.write('  Receptionists:  receptionist/recep123, reception/recep123')
        self.stdout.write('  Doctors:        dr_hira, dr_saba, dr_taj, dr_idrees, dr_ahmed (all: doctor123)')
        self.stdout.write('  Patients:       hamza, sara, usman (all: patient123)')
        self.stdout.write('='*80)
