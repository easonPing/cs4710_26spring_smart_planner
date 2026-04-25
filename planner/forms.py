from django import forms

from .models import CalendarEvent, Task, UserProfile

WEEKDAY_CHOICES = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
]


class ICSUploadForm(forms.Form):
    ics_file = forms.FileField(help_text='Upload an ICS calendar file.')

    def clean_ics_file(self):
        uploaded = self.cleaned_data['ics_file']
        if not uploaded.name.lower().endswith('.ics'):
            raise forms.ValidationError('Please upload an .ics file.')
        return uploaded


class SyllabusUploadForm(forms.Form):
    syllabus_file = forms.FileField(help_text='Upload a PDF or DOCX syllabus.')

    def clean_syllabus_file(self):
        uploaded = self.cleaned_data['syllabus_file']
        lower_name = uploaded.name.lower()
        if not (lower_name.endswith('.pdf') or lower_name.endswith('.docx')):
            raise forms.ValidationError('Please upload a PDF or DOCX file.')
        return uploaded


class CalendarEventForm(forms.ModelForm):
    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    end_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    repeat_weekdays = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Repeat weekly on',
        help_text='Leave unchecked for a single occurrence on the start date.',
    )

    class Meta:
        model = CalendarEvent
        fields = [
            'title',
            'start_datetime',
            'end_datetime',
            'event_type',
            'location',
            'description',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.recurrence_weekdays:
            self.initial.setdefault(
                'repeat_weekdays',
                [d for d in self.instance.recurrence_weekdays if isinstance(d, int) and 0 <= d <= 6],
            )

    def clean_repeat_weekdays(self):
        days = self.cleaned_data.get('repeat_weekdays') or []
        return sorted(set(days))


class TaskManualForm(forms.ModelForm):
    due_datetime = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )

    class Meta:
        model = Task
        fields = [
            'title',
            'course_name',
            'due_datetime',
            'estimated_minutes',
            'priority',
            'category',
            'status',
            'raw_excerpt',
        ]


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'display_name',
            'preferred_study_start',
            'preferred_study_end',
            'sleep_start',
            'sleep_end',
            'breakfast_start',
            'breakfast_end',
            'lunch_start',
            'lunch_end',
            'dinner_start',
            'dinner_end',
            'max_continuous_work_minutes',
            'default_break_minutes',
            'freeze_horizon_minutes',
        ]
        widgets = {
            field: forms.TimeInput(attrs={'type': 'time'})
            for field in [
                'preferred_study_start',
                'preferred_study_end',
                'sleep_start',
                'sleep_end',
                'breakfast_start',
                'breakfast_end',
                'lunch_start',
                'lunch_end',
                'dinner_start',
                'dinner_end',
            ]
        }


class NaturalLanguageUpdateForm(forms.Form):
    update_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Use natural language or JSON patch syntax to trigger replanning.',
    )


class ScheduleGenerationForm(forms.Form):
    target_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
