"""django_bootstrapper URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
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
from django.views.generic import TemplateView
from django.urls import path, include

from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', TemplateView.as_view(template_name='bootstrapper/welcome.html'), name='base'),
    path('login', auth_views.LoginView.as_view(template_name='base/login.html'), name='login'),
    path('logout', auth_views.LogoutView.as_view(next_page='login')),
    path('dynamic_content/', include('dynamic_content.urls')),
    # path('pan_tort/', include('pan_tort.urls')),
    path('bootstrapper/', include('bootstrapper.urls'))
]
