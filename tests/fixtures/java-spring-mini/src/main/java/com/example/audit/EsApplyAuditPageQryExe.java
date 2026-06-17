package com.example.audit;

import java.util.Map;

public class EsApplyAuditPageQryExe {
    private final ApplyAuditMapper mapper = null;

    public String execute(AuditStatus auditStatus) {
        return mapper.findByStatus(auditStatus.name());
    }

    public String involvedByMe(AuditStatus auditStatus) {
        if (auditStatus == AuditStatus.INVOLVED_BY_ME) {
            return mapper.findByStatus(auditStatus.name());
        }
        return "other";
    }

    public Map<String, Long> statsWait() {
        return Map.of("wait", 1L);
    }

    public WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry) {
        return new WorkbenchResourceAuditStatsDTO();
    }
}
