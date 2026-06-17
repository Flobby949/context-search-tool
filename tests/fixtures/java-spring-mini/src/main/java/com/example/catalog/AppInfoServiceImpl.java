package com.example.catalog;

public class AppInfoServiceImpl implements AppInfoService {
    private final PageAppCatalogQueryExe pageAppCatalogQueryExe;

    public AppInfoServiceImpl(PageAppCatalogQueryExe pageAppCatalogQueryExe) {
        this.pageAppCatalogQueryExe = pageAppCatalogQueryExe;
    }

    @Override
    public String page(AppCatalogPageQry qry) {
        return pageAppCatalogQueryExe.execute(qry);
    }
}
