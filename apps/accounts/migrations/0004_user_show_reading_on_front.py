from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_show_review_interval'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='show_reading_on_front',
            field=models.BooleanField(default=True),
        ),
    ]
