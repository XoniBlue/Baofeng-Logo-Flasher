interface ImagePanelProps {
  previewUrl: string;
  selectedFileName: string;
  onSelectFile: (file: File) => Promise<void>;
}

/** Step 2 UI for image file selection, filename display, and processed preview. */
export function ImagePanel({ previewUrl, selectedFileName, onSelectFile }: ImagePanelProps): JSX.Element {
  return (
    <section className="panel">
      <h2>Step 2 - Logo Image</h2>
      <input
        type="file"
        accept=".bmp,.png,.jpg,.jpeg,.gif,.webp,.tiff"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) {
            void onSelectFile(file);
          }
        }}
      />
      
      {selectedFileName && (
        <div className="file-info">
          <span className="file-icon">📄</span>
          <span className="file-name" title={selectedFileName}>
            {selectedFileName}
          </span>
        </div>
      )}
      
      {previewUrl ? <img className="preview" src={previewUrl} alt="processed logo preview" /> : null}
    </section>
  );
}
