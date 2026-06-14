package com.example.audit;

import java.util.Map;

public class ResourceAuditServiceImpl implements ResourceAuditService {
    private final EsApplyAuditPageQryExe esApplyAuditPageQryExe;

    public ResourceAuditServiceImpl(EsApplyAuditPageQryExe esApplyAuditPageQryExe) {
        this.esApplyAuditPageQryExe = esApplyAuditPageQryExe;
    }

    public Map<String, Long> statsWait() {
        return esApplyAuditPageQryExe.statsWait();
    }

    public WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry) {
        return esApplyAuditPageQryExe.auditStats(qry);
    }
}
