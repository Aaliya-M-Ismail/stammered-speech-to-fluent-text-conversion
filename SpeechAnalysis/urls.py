"""
URL configuration for SpeechAnalysis project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from App import views as app_views


urlpatterns = [
    path('', app_views.index, name='index'),
    path('signup/', app_views.signup_page, name='signup_page'),
    path('login/', app_views.login_page, name='login_page'),
    path('logout/', app_views.logout_view, name='logout'),
    path('speech/', app_views.speech, name='speech'),
    path('admin-dashboard/', app_views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/user/<int:user_id>/', app_views.admin_user_view, name='admin_user_view'),
    path('admin-dashboard/user/<int:user_id>/edit/', app_views.admin_user_edit, name='admin_user_edit'),
    path('admin-dashboard/user/<int:user_id>/delete/', app_views.admin_user_delete, name='admin_user_delete'),
    path('admin-dashboard/api/user/<int:user_id>/', app_views.admin_user_api, name='admin_user_api'),
    path('admin-dashboard/api/user/<int:user_id>/update/', app_views.admin_user_update, name='admin_user_update'),
    path('api/process-speech-tts/', app_views.process_speech_tts, name='process_speech_tts'),
    path('api/speech-history/', app_views.get_speech_history, name='get_speech_history'),
    
    # Chat room API endpoints
    path('api/chat/create/', app_views.create_chat_room, name='create_chat_room'),
    path('api/chat/join/', app_views.join_chat_room, name='join_chat_room'),
    path('api/chat/rooms/', app_views.get_user_rooms, name='get_user_rooms'),
    path('api/chat/room/<str:room_code>/', app_views.get_chat_room, name='get_chat_room'),
    path('api/chat/room/<str:room_code>/leave/', app_views.leave_chat_room, name='leave_chat_room'),
    
    path('admin/', admin.site.urls),
]
