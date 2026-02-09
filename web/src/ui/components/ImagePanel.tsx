interface ImagePanelProps {
  previewUrl: string;
  onSelectFile: (file: File) => Promise<void>;
}

export function ImagePanel({ previewUrl, onSelectFile }: ImagePanelProps): JSX.Element {
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
      {previewUrl ? <img className="preview" src={previewUrl} alt="processed logo preview" /> : null}
    </section>
  );
}
