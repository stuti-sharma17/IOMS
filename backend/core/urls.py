from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet
from .views import (
    LoginView, LogoutView,
    ProductListCreateView, ProductDetailView,
    CustomerListCreateView, CustomerDetailView,
    DashboardAPIView
)

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')


urlpatterns = [
    path('login/', LoginView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('products/', ProductListCreateView.as_view()),
    path('products/<int:pk>/', ProductDetailView.as_view()),    
    path('customers/', CustomerListCreateView.as_view()),
    path('customers/<int:pk>/', CustomerDetailView.as_view()),
    path('dashboard/', DashboardAPIView.as_view()),
]
urlpatterns += router.urls
