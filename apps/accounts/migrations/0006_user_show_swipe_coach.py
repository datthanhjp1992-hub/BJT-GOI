from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_user_color_scheme'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='show_swipe_coach',
            field=models.BooleanField(default=True),
        ),
    ]
