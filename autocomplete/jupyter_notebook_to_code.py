from nbconvert import PythonExporter
import nbformat


def notebook_to_code(notebook_path):
  nb = nbformat.read(notebook_path, nbformat.NO_CONVERT)
  exporter = PythonExporter()
  source, meta = exporter.from_notebook_node(nb)
  return source
