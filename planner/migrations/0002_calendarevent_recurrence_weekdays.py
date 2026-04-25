from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='calendarevent',
            name='recurrence_weekdays',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='0=Monday … 6=Sunday. Empty means a one-time event on start date.',
            ),
        ),
    ]
