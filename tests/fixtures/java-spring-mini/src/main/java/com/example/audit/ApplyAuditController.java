package com.example.audit;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    @PostMapping("/pageEs")
    public String pageEs(EsApplyAuditPageQryExe query) {
        return query.execute(AuditStatus.INVOLVED_BY_ME);
    }
}
