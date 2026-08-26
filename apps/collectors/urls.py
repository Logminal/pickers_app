from django.urls import path

from .views import (
    ChangeRequestListView,
    ChangeRequestReviewView,
    CollectorBlockView,
    CollectorDeleteView,
    CollectorNoteCreateView,
    CollectorProfileDetailView,
    CollectorRatingOverrideView,
    CollectorRegisterView,
    CollectorUnblockView,
    MyProfileView,
    PassportScanView,
    ProfileEditView,
)

urlpatterns = [
    path('register/', CollectorRegisterView.as_view(), name='collector_register'),
    path('manager/collectors/<int:user_id>/', CollectorProfileDetailView.as_view(), name='collector_profile_detail'),
    path('manager/collectors/<int:user_id>/passport-scan/', PassportScanView.as_view(), name='passport_scan_view'),
    path('manager/collectors/<int:user_id>/notes/add/', CollectorNoteCreateView.as_view(), name='collector_note_add'),
    path('manager/collectors/<int:user_id>/block/', CollectorBlockView.as_view(), name='collector_block'),
    path('manager/collectors/<int:user_id>/unblock/', CollectorUnblockView.as_view(), name='collector_unblock'),
    path(
        'manager/collectors/<int:user_id>/rating-override/',
        CollectorRatingOverrideView.as_view(), name='collector_rating_override',
    ),
    path('manager/collectors/<int:user_id>/delete/', CollectorDeleteView.as_view(), name='collector_delete'),

    path('my-profile/', MyProfileView.as_view(), name='my_profile'),
    path('my-profile/edit/', ProfileEditView.as_view(), name='profile_edit'),

    path('manager/change-requests/', ChangeRequestListView.as_view(), name='change_requests_list'),
    path('manager/change-requests/<int:pk>/review/', ChangeRequestReviewView.as_view(), name='change_request_review'),
]
