"""Neo4j client wrapper for Enterprise KG."""
from __future__ import annotations

import os
from typing import Any
from project.backend.core.config import get_service_config

try:
    from project.backend.knowledge_graph.schema import KGNode, KGRelation
except ModuleNotFoundError:
    from backend.knowledge_graph.schema import KGNode, KGRelation


class EnterpriseNeo4jClient:
    """Thin Neo4j client wrapper with lazy optional dependency."""

    def __init__(self, uri: str | None = None, username: str | None = None, password: str | None = None) -> None:
        service_config = get_service_config()
        self.uri = uri or service_config.neo4j_uri
        self.username = username or service_config.neo4j_username
        self.password = password or service_config.neo4j_password
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError("Install neo4j to use EnterpriseNeo4jClient online mode.") from exc
            self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def upsert_nodes(self, nodes: list[KGNode]) -> int:
        query = """
        UNWIND $nodes AS node
        MERGE (n:EnterpriseEntity {node_id: node.node_id})
        SET n.name = node.name,
            n.type = node.type,
            n.properties = node.properties
        """
        self.query(query, {"nodes": [_node_payload(node) for node in nodes]})
        return len(nodes)

    def upsert_relations(self, relations: list[KGRelation]) -> int:
        query = """
        UNWIND $relations AS rel
        MATCH (source:EnterpriseEntity {node_id: rel.source_id})
        MATCH (target:EnterpriseEntity {node_id: rel.target_id})
        MERGE (source)-[r:RELATED {type: rel.type}]->(target)
        SET r.properties = rel.properties
        """
        self.query(query, {"relations": [_relation_payload(relation) for relation in relations]})
        return len(relations)

    def query(self, cypher: str, parameters: dict | None = None) -> list[dict[str, Any]]:
        with self._get_driver().session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]


def _node_payload(node: KGNode) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "type": node.type.value,
        "name": node.name,
        "properties": node.properties,
    }


def _relation_payload(relation: KGRelation) -> dict[str, Any]:
    return {
        "source_id": relation.source_id,
        "target_id": relation.target_id,
        "type": relation.type.value,
        "properties": relation.properties,
    }


def render_constraints_cypher() -> str:
    return (
        "CREATE CONSTRAINT enterprise_entity_node_id IF NOT EXISTS "
        "FOR (n:EnterpriseEntity) REQUIRE n.node_id IS UNIQUE;"
    )
