package com.example.order;

import org.springframework.stereotype.Service;

@Service
final class DefaultOrderService implements OrderService {
    private final OrderMapper orderMapper;

    DefaultOrderService(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }

    @Override
    public Order create(OrderDto dto) {
        Order order = new Order(dto.id());
        orderMapper.insert(order);
        return order;
    }
}
