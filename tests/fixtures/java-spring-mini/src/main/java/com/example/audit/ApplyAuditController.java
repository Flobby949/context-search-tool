package com.example.audit;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    private final ResourceAuditService resourceAuditService;

    public ApplyAuditController(ResourceAuditService resourceAuditService) {
        this.resourceAuditService = resourceAuditService;
    }

    @PostMapping("/pageEs")
    public String pageEs(EsApplyAuditPageQryExe query) {
        return query.execute(AuditStatus.INVOLVED_BY_ME);
    }

    /**
     * 工作台相关代码
     * 工作台统计-待我审核
     */
    @GetMapping("/stats/wait")
    public Map<String, Long> statsWait() {
        return resourceAuditService.statsWait();
    }

    /**
     * 工作台统计-审核列表
     */
    @PostMapping("/stats")
    public WorkbenchResourceAuditStatsDTO auditStats(@RequestBody ApplyAuditEsSearchQry qry) {
        return resourceAuditService.auditStats(qry);
    }
}

interface ResourceAuditService {
    String applyPageEs(AuditStatus auditStatus);

    Map<String, Long> statsWait();

    WorkbenchResourceAuditStatsDTO auditStats(ApplyAuditEsSearchQry qry);
}

class ApplyAuditEsSearchQry {
}

class WorkbenchResourceAuditStatsDTO {
}
