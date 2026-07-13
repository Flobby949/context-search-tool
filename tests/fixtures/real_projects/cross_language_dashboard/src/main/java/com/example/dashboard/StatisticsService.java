package com.example.dashboard;

public final class StatisticsService {
    private final ChartService chartService = new ChartService();

    public String statistics() {
        return chartService.chartData();
    }
}
