package com.example.audit;

import org.apache.ibatis.annotations.Select;

public interface ApplyAuditMapper {
    @Select("SELECT * FROM apply_audit WHERE status = #{status}")
    String findByStatus(String status);
}
