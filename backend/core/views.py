from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework import status, generics, permissions
from .serializers import LoginSerializer, ProductSerializer, CustomerSerializer, OrderSerializer
from django.contrib.auth import logout
from .models import Product, Customer, Order
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.viewsets import ModelViewSet
from django.utils.timezone import now
from django.contrib.auth.models import User
from django.db.models import Sum, Count, ExpressionWrapper, F, DecimalField
from datetime import timedelta
from .models import Product, Order, OrderItem, Customer
from collections import defaultdict
from decimal import Decimal
from django.db.models.functions import TruncMonth


class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"token": token.key})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        request.user.auth_token.delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

class ProductListCreateView(generics.GenericAPIView):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        queryset = self.get_queryset()

    # Filter via query params
        status_filter = request.query_params.get('status')  # 'active', 'inactive'
        stock_filter = request.query_params.get('stock')    # 'low', 'out'

        if status_filter:
            status_filter = status_filter.strip('"')  # remove accidental quotes
            if status_filter in ['active', 'inactive']:
                queryset = queryset.filter(status=status_filter)

        if stock_filter == 'low':
            queryset = queryset.filter(stock__gt=0, stock__lt=5)
        elif stock_filter == 'out':
            queryset = queryset.filter(stock=0)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # calls create() or update() inside the serializer
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProductDetailView(generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return Product.objects.get(pk=pk)

    def get(self, request, pk):
        product = self.get_object(pk)
        serializer = self.get_serializer(product)
        return Response(serializer.data)

    def patch(self, request, pk):
        product = self.get_object(pk)
        serializer = self.get_serializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        product = self.get_object(pk)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CustomerListCreateView(generics.ListCreateAPIView):
    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

class OrderViewSet(ModelViewSet):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = self.queryset
        status_filter = self.request.query_params.get('status')

        valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]

        if status_filter:
            if status_filter in valid_statuses:
                queryset = queryset.filter(status=status_filter)
            else:
                return queryset.none() 

        return queryset

class DashboardAPIView(APIView):
        def get(self, request):
            today = now().date()
            start_of_month = today.replace(day=1)
            
            # orders = (
            #     Order.objects.annotate(
            #         total=Sum(
            #             ExpressionWrapper(F('items__product__price') * F('items__quantity'),
            #                             output_field=DecimalField())
            #         )
            #     )
            #     .values('id', 'customer__name', 'created_at', 'status', 'total')
            # )
            orders_this_month = Order.objects.filter(created_at__date__gte=start_of_month)
            orders_this_month_count = orders_this_month.count()

            revenue_this_month = sum(order.total for order in orders_this_month)

            active_products_count = Product.objects.filter(status='active').count()
            total_customers = Customer.objects.count()

            # Monthly revenue chart
            monthly_revenue_qs = (
                OrderItem.objects
                .annotate(
                    month=TruncMonth('order__created_at'),
                    subtotal=ExpressionWrapper(F('product__price') * F('quantity'), output_field=DecimalField())
                )
                .values('month')
                .annotate(revenue=Sum('subtotal'))
                .order_by('month')
        )

            monthly_revenue_list = [
                {
                    "month": entry["month"].strftime("%b"),
                    "revenue": float(entry["revenue"])
                }
                for entry in monthly_revenue_qs
            ]

            # Top 5 selling products
            top_products = (
                OrderItem.objects
                .values('product__id', 'product__name')
                .annotate(total_quantity=Sum('quantity'))
                .order_by('-total_quantity')[:5]
            )

            # Low stock products
            low_stock_products = Product.objects.filter(stock__lt=5).values('id', 'name', 'stock')

            # Recent Orders

            recent_orders = (
                Order.objects
                .annotate(
                    total=Sum(
                        ExpressionWrapper(
                            F('items__product__price') * F('items__quantity'),
                            output_field=DecimalField()
                        )
                    )
                )
                .select_related('customer')
                .order_by('-created_at')[:5]
                .values('id', 'customer__name', 'created_at', 'status', 'total')
            )

            return Response({
                "orders_this_month": orders_this_month_count,
                "revenue_this_month": float(revenue_this_month),
                "active_products_count": active_products_count,
                "total_customers": total_customers,
                "monthly_revenue": monthly_revenue_list,
                "top_products": list(top_products),
                "low_stock_products": list(low_stock_products),
                "recent_orders": list(recent_orders),
            })