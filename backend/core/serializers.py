from django.contrib.auth import authenticate
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Product, Customer, Order, OrderItem
from django.db import transaction
from django.db.models import F


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email/password.")
        
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid email/password.")

        data["user"] = user
        return data

class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.SerializerMethodField()
    is_out_of_stock = serializers.SerializerMethodField()
    class Meta:
        model = Product
        fields = '__all__'
    def get_is_low_stock(self, obj):
        return obj.is_low_stock

    def get_is_out_of_stock(self, obj):
        return obj.is_out_of_stock


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

# core/serializers.py
class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'subtotal']

class OrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    total = serializers.ReadOnlyField()
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'customer', 'customer_name', 'status', 'created_at', 'total', 'items']

    def create(self, validated_data):
        items_data = validated_data.pop('items')  # Remove items from main data
        with transaction.atomic():
            order = Order.objects.create(**validated_data)

            for item_data in items_data:
                product = Product.objects.select_for_update().get(id=item_data['product'].id)

                quantity = item_data['quantity']

                # ✅ Check if product is active
                if product.status.lower() != "active":
                    raise serializers.ValidationError(
                        f"Product '{product.name}' is inactive and cannot be ordered."
                    )

                # ✅ Check stock availability
                if product.stock < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for '{product.name}'. Available: {product.stock}, requested: {quantity}."
                    )

                # ✅ Deduct stock atomically using F()
                product.stock = F('stock') - quantity
                product.save(update_fields=['stock'])
                # Create order item
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price_at_purchase=product.price  # ✅ capture price at time of order
                )
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        instance.status = validated_data.get('status', instance.status)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                OrderItem.objects.create(
                    order=instance,
                    product=item_data['product'],
                    quantity=item_data['quantity'],
                    price_at_purchase=item_data['product'].price
                )

        return instance
