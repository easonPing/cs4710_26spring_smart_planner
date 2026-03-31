from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('calendar/upload/', views.calendar_upload_view, name='calendar_upload'),
    path('syllabus/upload/', views.syllabus_upload_view, name='syllabus_upload'),
    path('tasks/', views.task_list_view, name='task_list'),
    path('tasks/review/', views.task_review_view, name='task_review'),
    path('schedule/', views.daily_schedule_view, name='daily_schedule'),
    path('schedule/generate/', views.generate_daily_schedule_view, name='generate_daily_schedule'),
    path('schedule/apply-update/', views.apply_patch_view, name='apply_patch'),
    path('replans/', views.replan_logs_view, name='replan_logs'),
]
