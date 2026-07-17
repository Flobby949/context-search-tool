package com.example.order;

import org.apache.ibatis.annotations.Mapper;

@Mapper
interface OrderMapper {
    int insert(Order order);
}
