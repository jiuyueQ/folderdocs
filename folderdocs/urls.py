from django.contrib.auth import views as auth_views
from django.urls import path
from documents import views

urlpatterns = [
    path('', views.library, name='library'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('folders/create/', views.create_folder, name='create_folder'),
    path('folders/<uuid:pk>/delete/', views.delete_folder, name='delete_folder'),
    path('upload/', views.upload, name='upload'),
    path('documents/<uuid:pk>/', views.detail, name='detail'),
    path('documents/<uuid:pk>/file/', views.file_view, name='file'),
    path('documents/<uuid:pk>/thumbnail/', views.thumbnail, name='thumbnail'),
    path('documents/<uuid:pk>/retry/', views.retry, name='retry'),
    path('documents/<uuid:pk>/move/', views.move, name='move'),
    path('documents/<uuid:pk>/delete/', views.delete, name='delete'),
    path('documents/<uuid:pk>/restore/', views.restore, name='restore'),
    path('documents/<uuid:pk>/purge/', views.purge, name='purge'),
    path('status/', views.status, name='status'),
]
