import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.project.settings')
django.setup()

from backend.apps.accounts.models import User

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
        print(f"✓ Created receptionist: {data['username']} / {data['password']}")
    else:
        print(f"- Receptionist {data['username']} already exists")

print("\n" + "="*60)
print("RECEPTIONIST ACCOUNTS:")
print("  Username: receptionist | Password: recep123")
print("  Username: reception    | Password: recep123")
print("="*60)
