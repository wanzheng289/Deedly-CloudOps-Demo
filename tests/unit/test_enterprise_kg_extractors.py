from backend.knowledge_graph.entity_extractor import extract_enterprise_entities
from backend.knowledge_graph.relation_extractor import extract_enterprise_relations


def test_support_ticket_extraction_builds_customer_ticket_product_relations():
    record = {
        "ticket_id": "C1",
        "customer_id": "Cust1",
        "product": "SSO",
        "issue_type": "Login Failure",
        "status": "open",
        "priority": "high",
        "summary": "Customer cannot login.",
    }

    nodes = extract_enterprise_entities(record)
    relations = extract_enterprise_relations(record, nodes)

    node_types = {node.type.value for node in nodes}
    relation_types = {relation.type.value for relation in relations}

    assert {"Customer", "SupportTicket", "Product", "Issue", "FAQ"}.issubset(node_types)
    assert "CUSTOMER_OPENED_TICKET" in relation_types
    assert "TICKET_MENTIONS_PRODUCT" in relation_types
    assert "TICKET_HAS_ISSUE" in relation_types


def test_document_extraction_builds_document_service_module_relations():
    record = {
        "doc_id": "doc1",
        "source_type": "confluence",
        "title": "Runbook: Deploy perf-canary",
        "content": "Owners: Runtime Team\nDeploy perf-canary in prod with helm and telemetry checks.",
    }

    nodes = extract_enterprise_entities(record)
    relations = extract_enterprise_relations(record, nodes)

    node_types = {node.type.value for node in nodes}
    relation_types = {relation.type.value for relation in relations}

    assert "Document" in node_types
    assert "Service" in node_types
    assert "Module" in node_types
    assert "DOCUMENT_FROM_SOURCE" in relation_types
    assert "DOCUMENT_MENTIONS_SERVICE" in relation_types
