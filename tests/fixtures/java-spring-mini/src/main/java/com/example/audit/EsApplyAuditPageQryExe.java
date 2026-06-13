package com.example.audit;

public class EsApplyAuditPageQryExe {
    private final ApplyAuditMapper mapper = null;

    public String execute(AuditStatus auditStatus) {
        return mapper.findByStatus(auditStatus.name());
    }
}
