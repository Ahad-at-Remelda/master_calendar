# scheduler_app/forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import Event

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'date', 'start_time', 'end_time', 'location']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control'}),
            'date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}
            ),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            #'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        """
        This is where we add our custom validation logic.
        """
        cleaned_data = super().clean()
        
        # Get the values of the fields from the form
        date = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        # --- Rule #1: Start and End times must be on the same day as the Date field ---
        if date and start_time and (date != start_time.date()):
            # If the date of the start_time is not the same as the main date,
            # raise a validation error that will be displayed to the user.
            raise ValidationError(
                "Inconsistency found: The Start Time's date must be the same as the main Event Date."
            )
        
        if date and end_time and (date != end_time.date()):
            # Do the same check for the end_time.
            raise ValidationError(
                "Inconsistency found: The End Time's date must be the same as the main Event Date."
            )

        # --- Rule #2: End time must be after start time ---
        if start_time and end_time and (end_time < start_time):
            raise ValidationError(
                "Invalid time range: The End Time must be after the Start Time."
            )

        return cleaned_data
    
