from django.core.management.base import BaseCommand
from backend.apps.accounts.models import User


class Command(BaseCommand):
    help = 'Fix receptionist account password'

    def handle(self, *args, **options):
        self.stdout.write('Fixing receptionist passwords...')
        
        # Fix receptionist account
        try:
            user = User.objects.get(username='receptionist')
            user.set_password('recep123')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Fixed password for: receptionist'))
            self.stdout.write(f'  Username: {user.username}')
            self.stdout.write(f'  Name: {user.first_name} {user.last_name}')
            self.stdout.write(f'  Email: {user.email}')
            self.stdout.write(f'  Password: recep123')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('✗ User "receptionist" not found'))
        
        self.stdout.write('')
        
        # Fix reception account
        try:
            user = User.objects.get(username='reception')
            user.set_password('recep123')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Fixed password for: reception'))
            self.stdout.write(f'  Username: {user.username}')
            self.stdout.write(f'  Name: {user.first_name} {user.last_name}')
            self.stdout.write(f'  Email: {user.email}')
            self.stdout.write(f'  Password: recep123')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('✗ User "reception" not found'))
        
        self.stdout.write('')
        self.stdout.write('='*70)
        self.stdout.write('RECEPTIONIST LOGIN CREDENTIALS:')
        self.stdout.write('  Username: receptionist | Password: recep123')
        self.stdout.write('  Username: reception    | Password: recep123')
        self.stdout.write('='*70)
        self.stdout.write('')
        self.stdout.write('✅ Try logging in again now!')
