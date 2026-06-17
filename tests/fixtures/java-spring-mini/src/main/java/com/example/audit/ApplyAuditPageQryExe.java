package com.example.audit;

public class ApplyAuditPageQryExe {
    public String applyPage(AuditStatus auditStatus) {
        return "non-es-" + auditStatus.name();
    }
}
