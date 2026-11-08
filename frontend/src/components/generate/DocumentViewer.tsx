import "./DocumentViewer.css";

/** create.md sec.9 - renders the Generated Document's HTML (headings,
 * paragraphs, tables, lists, checkboxes, basic formatting) - never the
 * raw DOCX binary. Read-only; see DocumentEditor for the editable mode. */
export function DocumentViewer({ html }: { html: string }) {
  return <div className="document-viewer" dangerouslySetInnerHTML={{ __html: html }} />;
}
