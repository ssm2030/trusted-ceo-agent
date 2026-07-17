from __future__ import annotations

# Independent fixture; production constants are intentionally not imported.

from typing import Any


ACCOUNTING_TABLE_NAMES = (
    "allocation_drivers", "allocation_pools", "allocation_results",
    "bank_accounts", "bank_transactions", "budgets", "cash_receipts",
    "chart_of_accounts", "contract_amendments", "contracts", "credit_notes",
    "customers", "departments", "direct_costs", "employee_assignments",
    "employees", "forecasts", "indirect_costs", "invoices",
    "journal_headers", "journal_lines", "management_kpis", "milestones",
    "payable_aging", "payroll_costs", "performance_obligations", "projects",
    "receivable_aging", "trial_balance", "vendor_costs", "vendor_payments",
    "vendors", "work_logs",
)


def valid_accounting_multitable_document() -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ACCOUNTING_TABLE_NAMES
    }
    tables["chart_of_accounts"] = [
        {
            "account_code": "2000", "account_id": "ACC-AP",
            "account_name": "Accounts payable", "account_type": "liability",
            "active": True, "currency": "KRW", "entity": "E1",
            "normal_balance": "credit",
        },
        {
            "account_code": "5000", "account_id": "ACC-EXP",
            "account_name": "Project expense", "account_type": "expense",
            "active": True, "currency": "KRW", "entity": "E1",
            "normal_balance": "debit",
        },
    ]
    tables["customers"] = [{
        "business_number": "123-45-67890", "country_code": "KR",
        "credit_terms_days": 30, "customer_id": "C1",
        "customer_name": "Customer One", "entity": "E1",
        "industry": None,
    }]
    tables["departments"] = [{
        "cost_center": "CC1", "department_id": "D1",
        "department_name": "Finance", "entity": "E1",
    }]
    tables["employees"] = [
        {
            "active": True, "currency": "KRW", "department_id": "D1",
            "employee_id": "U1", "employee_name": "Creator",
            "entity": "E1", "hire_date": "2025-01-01",
            "job_title": "Accountant", "monthly_salary": "10.00",
        },
        {
            "active": True, "currency": "KRW", "department_id": "D1",
            "employee_id": "U2", "employee_name": "Approver",
            "entity": "E1", "hire_date": "2025-01-01",
            "job_title": "Controller", "monthly_salary": "10.00",
        },
    ]
    tables["projects"] = [{
        "budget_amount": "200.00", "currency": "KRW",
        "customer_id": "C1", "department_id": "D1",
        "end_date": "2026-12-31", "entity": "E1",
        "fixed_price": "200.00", "project_id": "P1",
        "project_manager_employee_id": "U1", "project_name": "Project One",
        "start_date": "2026-01-01", "status": "active",
    }]
    tables["vendors"] = [{
        "business_number": "123-45-67890", "country_code": "KR",
        "entity": "E1", "payment_terms_days": 30,
        "service_category": "cloud", "vendor_id": "V1",
        "vendor_name": "Vendor One",
    }]
    tables["journal_headers"] = [{
        "approved_at": "2026-06-30T10:05:00Z", "approver_id": "U2",
        "counterparty_id": "V1", "creator_id": "U1",
        "creator_role": "accountant", "currency": "KRW",
        "description": "June service", "economic_event_date": "2026-06-29",
        "entered_at": "2026-06-30T10:00:00Z", "entity": "E1",
        "journal_id": "J1", "period": "2026-06",
        "posting_date": "2026-06-30", "project_id": "P1",
        "sequence": 1, "source_id": "ledger", "source_type": "manual",
        "status": "posted",
    }]
    tables["journal_lines"] = [
        {
            "account_id": "ACC-EXP", "credit": "0.00",
            "currency": "KRW", "debit": "100.00", "entity": "E1",
            "journal_id": "J1", "line_id": "L1", "line_number": 1,
            "period": "2026-06", "project_id": "P1",
        },
        {
            "account_id": "ACC-AP", "credit": "100.00",
            "currency": "KRW", "debit": "0.00", "entity": "E1",
            "journal_id": "J1", "line_id": "L2", "line_number": 2,
            "period": "2026-06", "project_id": "P1",
        },
    ]
    tables["trial_balance"] = [
        {
            "account_id": "ACC-EXP", "closing": "100.00",
            "control_subledger": "not_applicable", "credit_turnover": "0.00",
            "currency": "KRW", "debit_turnover": "100.00", "entity": "E1",
            "opening": "0.00", "period": "2026-06",
            "prior_closing": "0.00", "trial_balance_id": "TB-EXP",
        },
        {
            "account_id": "ACC-AP", "closing": "-100.00",
            "control_subledger": "payable_aging", "credit_turnover": "100.00",
            "currency": "KRW", "debit_turnover": "0.00", "entity": "E1",
            "opening": "0.00", "period": "2026-06",
            "prior_closing": "0.00", "trial_balance_id": "TB-AP",
        },
    ]
    tables["vendor_costs"] = [{
        "amount": "100.00", "cost_date": "2026-06-29",
        "currency": "KRW", "direct_flag": True, "entity": "E1",
        "invoice_reference": "INV-V1", "journal_id": "J1",
        "project_id": "P1", "service_category": "cloud",
        "vendor_cost_id": "VC1", "vendor_id": "V1",
    }]
    tables["payable_aging"] = [{
        "aging_bucket": "current", "ap_item_id": "AP1",
        "as_of_date": "2026-06-30", "currency": "KRW", "entity": "E1",
        "original_amount": "100.00", "outstanding_amount": "100.00",
        "vendor_cost_id": "VC1", "vendor_id": "V1",
    }]
    tables["direct_costs"] = [{
        "amount": "80.00", "cost_date": "2026-06-29",
        "cost_type": "vendor", "currency": "KRW",
        "direct_cost_id": "DC1", "entity": "E1", "project_id": "P1",
        "source_row_id": "VC1", "source_table": "vendor_costs",
    }]
    tables["allocation_pools"] = [{
        "account_id": "ACC-EXP", "currency": "KRW",
        "driver_type": "approved_engineer_hours", "entity": "E1",
        "period": "2026-06", "pool_id": "POOL1",
        "pool_name": "Operations", "source_amount": "120.00",
    }]
    tables["allocation_drivers"] = [{
        "driver_id": "DRV1", "driver_quantity": "3.00",
        "driver_share": "1.00", "entity": "E1", "period": "2026-06",
        "pool_id": "POOL1", "project_id": "P1",
    }]
    tables["allocation_results"] = [{
        "allocated_amount": "100.00", "allocation_id": "ALLOC1",
        "currency": "KRW", "driver_id": "DRV1", "entity": "E1",
        "journal_id": "J1", "period": "2026-06",
        "pool_id": "POOL1", "project_id": "P1",
    }]
    return {
        "company_id": "COMP1",
        "company_name": "Company One",
        "currency": "KRW",
        "entity": "E1",
        "generator_version": "1.0.0",
        "reporting_period": {"start": "2026-01-01", "end": "2026-06-30"},
        "scenario_id": "unit-valid",
        "schema_version": "1.0.0",
        "seed": 1,
        "tables": tables,
    }
