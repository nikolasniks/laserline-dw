-- 006_views.sql
-- Handy views for BI and for the weekly report job.

CREATE OR REPLACE VIEW dw.v_sales_daily AS
SELECT d.full_date,
       COUNT(DISTINCT f.order_id) AS orders,
       SUM(f.quantity)            AS items,
       SUM(f.line_total)          AS revenue,
       SUM(f.area_m2 * f.quantity) AS area_m2
FROM dw.fact_order_line f
JOIN dw.dim_date d ON d.date_key = f.order_date_key
GROUP BY d.full_date;

CREATE OR REPLACE VIEW dw.v_top_customers_90d AS
SELECT c.customer_id, c.name,
       COUNT(DISTINCT f.order_id) AS orders,
       SUM(f.line_total)          AS revenue
FROM dw.fact_order_line f
JOIN dw.dim_customer c ON c.customer_sk = f.customer_sk
JOIN dw.dim_date d     ON d.date_key = f.order_date_key
WHERE d.full_date >= current_date - INTERVAL '90 days'
GROUP BY c.customer_id, c.name
ORDER BY revenue DESC;

CREATE OR REPLACE VIEW dw.v_top_products_90d AS
SELECT p.product_id, p.name,
       SUM(f.quantity)   AS qty,
       SUM(f.line_total) AS revenue
FROM dw.fact_order_line f
JOIN dw.dim_product p ON p.product_sk = f.product_sk
JOIN dw.dim_date d    ON d.date_key = f.order_date_key
WHERE d.full_date >= current_date - INTERVAL '90 days'
GROUP BY p.product_id, p.name
ORDER BY revenue DESC;

CREATE OR REPLACE VIEW dw.v_cash_position AS
SELECT 'receivable' AS side,
       COALESCE(SUM(CASE WHEN NOT is_paid THEN amount - amount_paid ELSE 0 END), 0) AS open_amount,
       SUM(CASE WHEN NOT is_paid AND d.full_date < current_date
                THEN amount - amount_paid ELSE 0 END) AS overdue
FROM dw.fact_receivable r
LEFT JOIN dw.dim_date d ON d.date_key = r.due_date_key
UNION ALL
SELECT 'payable',
       COALESCE(SUM(CASE WHEN NOT is_paid THEN amount - amount_paid ELSE 0 END), 0),
       SUM(CASE WHEN NOT is_paid AND d.full_date < current_date
                THEN amount - amount_paid ELSE 0 END)
FROM dw.fact_payable p
LEFT JOIN dw.dim_date d ON d.date_key = p.due_date_key;

-- Monthly view for the management dashboard: revenue, orders, ticket and MDF area.
CREATE OR REPLACE VIEW dw.v_sales_monthly AS
SELECT date_trunc('month', d.full_date)::date                       AS month,
       COUNT(DISTINCT f.order_id)                                   AS orders,
       SUM(f.line_total)                                            AS revenue,
       ROUND(SUM(f.line_total) / NULLIF(COUNT(DISTINCT f.order_id), 0), 2) AS avg_ticket,
       COALESCE(SUM(f.area_m2 * f.quantity), 0)                      AS area_m2
FROM dw.fact_order_line f
JOIN dw.dim_date d ON d.date_key = f.order_date_key
GROUP BY 1;

