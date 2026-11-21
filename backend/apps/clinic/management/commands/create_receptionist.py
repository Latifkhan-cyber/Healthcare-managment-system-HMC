from django.core.management.base import BaseCommand
from backend.apps.accounts.models import User


class Command(BaseCommand):
    help = 'Create receptionist accounts'

    def handle(self, *args, **options):
        self.stdout.write('Creating receptionist accounts...')

        # Create receptionist accounts
        receptionists_data = [
            {
                'username': 'receptionist',
                'first_name': 'Sarah',
                'last_name': 'Ahmed',
                'email': 'receptionist@clinic.com',
                'phone': '03001122334',
                'password': 'recep123'
            },
            {
                'username': 'reception',
                'first_name': 'Ayesha',
                'last_name': 'Khan',
                'email': 'reception@clinic.com',
                'phone': '03001122335',
                'password': 'recep123'
            }
        ]

        for data in receptionists_data:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'email': data['email'],
                    'phone': data['phone'],
                    'role': 'RECEPTIONIST',
                }
            )
            if created:
                user.set_password(data['password'])
                user.save()
                self.stdout.write(f"  ✓ Created receptionist: {data['username']}")
            else:
                self.stdout.write(f"  - Receptionist {data['username']} already exists")

        self.stdout.write(self.style.SUCCESS('\nDone! Receptionist accounts ready.'))
        self.stdout.write('')
        self.stdout.write('RECEPTIONIST ACCOUNTS:')
        self.stdout.write('  Username: receptionist | Password: recep123 (Sarah Ahmed)')
        self.stdout.write('  Username: reception    | Password: recep123 (Ayesha Khan)')
