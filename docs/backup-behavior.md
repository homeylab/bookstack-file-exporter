# Backup Behavior

[← Back to README](../README.md#documentation)

- [General](#general)
  - [File Naming](#file-naming)
  - [Directory Layout](#directory-layout)
  - [Empty/New Pages](#emptynew-pages)
- [Images](#images)
- [Attachments](#attachments)
- [Modify Links](#modify-links)
  - [Markdown example](#markdown-example)
  - [HTML example](#html-example)
  - [Known limitations](#known-limitations)

## General
Backups are exported in `.tgz` format and generated based off timestamp. Export names will be in the format: `%Y-%m-%d_%H-%M-%S` (Year-Month-Day_Hour-Minute-Second). *Files are first pulled locally to create the tarball and then can be sent to object storage if needed*. Example file name: `bookstack_export_2023-09-22_07-19-54.tgz`.

The exporter can also do housekeeping duties and keep a configured number of archives and delete older ones. See `keep_last` property in the [Configuration](configuration.md#options-and-descriptions) section. Object storage provider configurations include their own `keep_last` property for flexibility. 

### File Naming
For file names, `slug` names (from Bookstack API) are used, as such certain characters like `!`, `/` will be ignored and spaces replaced from page names/titles. If your page has an empty `slug` value for some reason (draft that was never fully saved), the exporter will use page name with the `slugify` function from Django to generate a valid slug. Example: `My Page.bin Name!` will be converted to `my-page-bin-name`.

You may also notice some directories (books) and/or files (pages) in the archive have a random string at the end, example - `nKA`: `user-and-group-management-nKA`. This is expected and is because there were resources with the same name created in another shelve and bookstack adds a string at the end to ensure uniqueness.

### Directory Layout
All sub directories will be created as required during the export process.
```
Shelves --> Books --> Chapters --> Pages

## Example
kafka (shelf)
---> controller (book)
    ---> settings (chapter)
        ---> retention-settings.md (page)
        ---> retention-settings_meta.json
            ...
        ---> compression.html (page)
        ---> compression.pdf
        ---> compression_meta.json
            ...
        ---> optional-config.md (page)
            ...
        ---> main.md (page)
            ...
---> broker (book)
    ---> settings.md (page)
        ...
    ---> deploy.md (page)
        ...
kafka-apps (shelf)
---> schema-registry (book)
    ---> protobuf.md (page)
        ...
    ---> settings.md (page)
        ...

## Example with image and attachment layout
# unassigned dir is used for books with no shelf
unassigned (shelf)
---> test (book)
    ---> images (image_dir)
        ---> test_page (page directory)
            ---> img-001.png
            ---> img-002.png
        ---> rec-page
            ---> img-010.png
            ---> img-020.png
    --> attachments (attachment_dir)
        ---> test_page (page directory)
            ---> something.config
            ---> something_else.config
        ---> rec-page
            ---> test_output.log
            ---> actual_output.log
    ---> test_page.md (page)
            ...
    ---> rec_page (page)
        ---> rec_page.md
        ---> rec_page.pdf

```

Another example is shown below:

```
## From first example above:
# programming = shelf
# book = react
# basics = page

bookstack_export_2023-11-28_06-24-25/programming/react/basics.md
bookstack_export_2023-11-28_06-24-25/programming/react/basics.pdf
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/YKvimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/dwwimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/NzZimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/next1.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/tips.png
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample.config
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample_output.log
bookstack_export_2023-11-28_06-24-25/programming/react/nextjs.md
bookstack_export_2023-11-28_06-24-25/programming/react/nextjs.pdf
```

Books without a shelf will be put in a shelve folder named `unassigned`.

### Empty/New Pages
Empty/New Pages are ignored: they have not been modified from creation, so they have no content and no valid slug. From the Bookstack API they appear as `"name": "New Page"` with an empty `"slug": ""`.

## Images
Images will be dumped in a separate directory, `images` within the page parent (book/chapter) directory it belongs to. The relative path will be `{parent}/images/{page}/{image_name}`. As shown earlier:

```
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/dwwimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/basics/NzZimage.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/next1.png
bookstack_export_2023-11-28_06-24-25/programming/react/images/nextjs/tips.png
```

**Note you may see old images in your exports. This is because, by default, Bookstack retains images/drawings that are uploaded even if no longer referenced on an active page. Admins can run `Cleanup Images` in the Maintenance Settings or via [CLI](https://www.bookstackapp.com/docs/admin/commands/#cleanup-unused-images) to remove them.**

If an API call to get an image or its metadata fails, the exporter will skip the image and log the error. If using `modify_links` option, the image links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

## Attachments
Attachments will be dumped in a separate directory, `attachments` within the page parent (book/chapter) directory it belongs to. The relative path will be `{parent}/attachments/{page}/{attachment_name}`. As shown earlier:

```
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample.config
bookstack_export_2023-11-28_06-24-25/programming/react/attachments/nextjs/sample_package.json
...
...
```

**Note attachments that are just external links are ignored. Only attachments that are shown as `external: False` will be exported.**

[Reference](https://demo.bookstackapp.com/api/docs#attachments-list) and excerpt from Bookstack API docs:
> Get a listing of attachments visible to the user. The external property indicates whether the attachment is simple a link. A false value for the external property would indicate a file upload.

If an API call to get an attachment or its metadata fails, the exporter will skip the attachment and log the error. If using `modify_links` option, the attachment links in the document will be untouched and in its original form. All API calls are retried 3 times after initial failure.

## Modify Links
**To use this feature, `assets.export_images` should be set to `true` and/or `assets.export_attachments` should be set to `true`.**

The configuration item, `assets.modify_links`, can be set to `true` to rewrite image and attachment URL links in exported files to local relative paths. This feature makes your `markdown` and `html` exports fully portable — assets resolve locally without a network connection to the Bookstack instance.

- **Eligible formats**: `markdown` and `html` only. PDF, plaintext, and zip exports are not yet requested/implemented.
- **Scope**: rewrites image `src` attributes and their outer anchor `href` wrappers; rewrites attachment `<a href>` links. Does **not** rewrite inter-page, inter-book, inter-chapter, or inter-shelf links (deferred to a future issue).
- **Removed key**: the legacy `modify_markdown` key was removed in v3.0.0. Rename it to `modify_links` in your configuration.

### Markdown example

```
## before
[![pool-topology-1.png](https://demo.bookstack/uploads/images/gallery/2023-07/scaled-1680-/pool-topology-1.png)](https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png)

## after
[![pool-topology-1.png](images/{page_name}/pool-topology-1.png)](images/{page_name}/pool-topology-1.png)
```

### HTML example

Bookstack HTML exports wrap images in an anchor tag (click-to-zoom). Both the
`<img src>` and the outer `<a href>` are rewritten to the same local file.
Images appear in one of two forms; both are localized:

```html
<!-- before: remote "scaled" thumbnail src (older bookstack installations) -->
<a href="https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png">
  <img src="https://demo.bookstack/uploads/images/gallery/2023-07/scaled-1680-/pool-topology-1.png">
</a>

<!-- before: inline base64 src (recent bookstack installations) -->
<a href="https://demo.bookstack/uploads/images/gallery/2023-07/pool-topology-1.png">
  <img src="data:image/png;base64,...">
</a>

<!-- after (both forms): src and href point at the one local file -->
<a href="images/{page_name}/pool-topology-1.png">
  <img src="images/{page_name}/pool-topology-1.png">
</a>
```

Inline base64 images are de-inlined to the local file (shrinking the export by
up to ~700 KB per full-size image). A base64 image **not** wrapped in a
downloadable anchor is left inline (it still resolves offline).

Attachment links are rewritten from the live URL to a local relative path.

```html
<!-- before: attachment link -->
<a href="https://demo.bookstack/attachments/42">my-config.yml</a>

<!-- after -->
<a href="attachments/{page_name}/my-config.yml">my-config.yml</a>
```

### Known limitations

Markdown link rewriting is a plain text substitution: if an asset URL appears verbatim anywhere in the markdown (code block, comment, plain text), it is also rewritten. HTML rewriting is scoped to `<img src>` / `<a href>` attributes only, so it is unaffected.

