package com.example.catalog;

public class PageAppCatalogQueryExe {
    public String execute(AppCatalogPageQry qry) {
        return fillCanApplyFilter(qry);
    }

    private String fillCanApplyFilter(AppCatalogPageQry qry) {
        if (Boolean.TRUE.equals(qry.getCanApply())) {
            return "canApply";
        }
        return "all";
    }
}
