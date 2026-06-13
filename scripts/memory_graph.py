"""Generates a GraphML file of the memory reference structure for a given project."""

import argparse
import xml.etree.ElementTree as ET

from serena.config.serena_config import SerenaConfig
from serena.memories.memory_reference_analysis import iter_referenced_names_in_content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a GraphML graph of memory references for a Serena project.")
    parser.add_argument("project", help="Name (or root path) of the registered project.")
    parser.add_argument("-o", "--output", default="memory_graph.graphml", help="Output file path (default: memory_graph.graphml).")
    args = parser.parse_args()

    # load project and its memory manager
    serena_config = SerenaConfig.from_config_file()
    project = serena_config.get_project(args.project)
    if project is None:
        raise SystemExit(f"Project '{args.project}' not found in Serena configuration.")
    mm = project.memory_manager

    # gather all project memory names
    memories_list = mm.list_project_memories()
    all_names = memories_list.get_full_list()

    # collect references by reading each memory's content
    edges: list[tuple[str, str]] = []
    node_names: set[str] = set(all_names)
    for name in all_names:
        content = mm.load_memory(name)
        for referenced in iter_referenced_names_in_content(content):
            edges.append((name, referenced))
            node_names.add(referenced)

    # build GraphML
    ns = "http://graphml.graphdrawing.org/xmlns"
    y_ns = "http://www.yworks.com/xml/graphml"
    graphml = ET.Element("graphml", xmlns=ns)
    graphml.set("xmlns:y", y_ns)

    ET.SubElement(graphml, "key", id="d0", **{"for": "node", "yfiles.type": "nodegraphics"})
    graph = ET.SubElement(graphml, "graph", id="memory_references", edgedefault="directed")

    for node_name in sorted(node_names):
        node = ET.SubElement(graph, "node", id=node_name)
        data = ET.SubElement(node, "data", key="d0")
        shape_node = ET.SubElement(data, "y:ShapeNode")
        label = ET.SubElement(shape_node, "y:NodeLabel")
        label.text = node_name

    for i, (source, target) in enumerate(edges):
        ET.SubElement(graph, "edge", id=f"e{i}", source=source, target=target)

    tree = ET.ElementTree(graphml)
    ET.indent(tree)
    tree.write(args.output, xml_declaration=True, encoding="utf-8")
    print(f"Wrote {len(node_names)} nodes and {len(edges)} edges to {args.output}")


if __name__ == "__main__":
    main()
