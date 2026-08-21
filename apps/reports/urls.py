from django.urls import path

from .views import ActUploadView, OrderCloseView, PhotoReportReviewView, PhotoReportUploadView

urlpatterns = [
    path('orders/<int:pk>/report/upload/', PhotoReportUploadView.as_view(), name='report_upload'),
    path('manager/orders/<int:pk>/report/review/', PhotoReportReviewView.as_view(), name='report_review'),
    path('manager/orders/<int:pk>/act/upload/', ActUploadView.as_view(), name='act_upload'),
    path('manager/orders/<int:pk>/close/', OrderCloseView.as_view(), name='order_close'),
]
