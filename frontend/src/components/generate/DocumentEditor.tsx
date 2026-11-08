import { useEffect, useRef } from "react";
import "./DocumentViewer.css";
import "./DocumentEditor.css";

interface Props {
  html: string;
  onChange: (html: string) => void;
}

/** create.md sec.10/29 - ONE contentEditable region, not scattered across
 * sub-components; `html` (documentDraft, owned by useDocument) is the
 * single source of truth. This element only reports changes upward via
 * onChange - it never keeps its own separate copy of the content. */
export function DocumentEditor({ html, onChange }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const initialHtml = useRef(html);

  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== initialHtml.current) {
      ref.current.innerHTML = initialHtml.current;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={ref}
      className="document-viewer document-editor"
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label="Document content editor"
      onInput={(event) => onChange(event.currentTarget.innerHTML)}
    />
  );
}
