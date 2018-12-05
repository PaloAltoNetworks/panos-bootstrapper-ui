from django.urls import path

from dynamic_content.views import *

app_name = 'dynamic_content'
urlpatterns = [
    path('', DownloadDynamicContentView.as_view()),
]
