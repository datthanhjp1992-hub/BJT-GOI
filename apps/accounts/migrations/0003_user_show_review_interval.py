from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_remove_user_target_bjt_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='show_review_interval',
            field=models.BooleanField(default=False),
        ),
    ]
