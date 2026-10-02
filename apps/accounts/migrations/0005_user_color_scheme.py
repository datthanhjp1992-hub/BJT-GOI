import apps.core.constants
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_user_show_reading_on_front'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='color_scheme',
            field=models.CharField(choices=apps.core.constants.color_scheme_choices, default='auto', help_text='MasterCode code_type 18: auto / light / dark.', max_length=10),
        ),
    ]
