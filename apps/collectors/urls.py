from django.urls import path

from .views import (
    ChangeRequestListView,
    ChangeRequestReviewView,
    CollectorProfileDetailView,
    CollectorRegisterView,
    MyProfileView,
    PassportScanView,
    ProfileEditView,
)

urlpatterns = [
    path('register/', CollectorRegisterView.as_view(), name='collector_register'),
    path('manager/collectors/<int:user_id>/', CollectorProfileDetailView.as_view(), name='collector_profile_detail'),
    path('manager/collectors/<int:user_id>/passport-scan/', PassportScanView.as_view(), name='passport_scan_view'),

    path('my-profile/', MyProfileView.as_view(), name='my_profile'),
    path('my-profile/edit/', ProfileEditView.as_view(), name='profile_edit'),

    path('manager/change-requests/', ChangeRequestListView.as_view(), name='change_requests_list'),
    path('manager/change-requests/<int:pk>/review/', ChangeRequestReviewView.as_view(), name='change_request_review'),
]
