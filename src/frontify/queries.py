# SPDX-License-Identifier: Apache-2.0
"""GraphQL documents. Every field used here was checked against
https://frontify.github.io/graphql-reference/ (see docs/FRONTIFY_API.md).

Each operation is *named* so it can be logged, traced and mocked in tests.
Assets come in two detail levels so the scanner can degrade gracefully if a given
Frontify instance rejects an optional field.
"""
from __future__ import annotations

CURRENT_USER = """query CurrentUser { currentUser { id name } }"""

ACCOUNT_BRANDS = """query Brands { brands { id name slug avatar } }"""

BRAND_LIBRARIES = """query BrandLibraries($id: ID!, $page: Int!, $limit: Int!) {
  brand(id: $id) { libraries(page: $page, limit: $limit) { total page limit hasNextPage items { id name } } }
}"""

BRAND_WORKSPACES = """query BrandWorkspaces($id: ID!, $page: Int!, $limit: Int!) {
  brand(id: $id) { workspaceProjects(page: $page, limit: $limit) { total page limit hasNextPage items { id name } } }
}"""

_USER = "{ id name }"

ASSET_FIELDS_FULL = f"""
  __typename id title description alternativeText externalId createdAt modifiedAt expiresAt author status
  creator {_USER} modifier {_USER}
  tags {{ value source }}
  customMetadata {{
    __typename
    property {{ id name }}
    ... on CustomMetadataValue {{ value }}
    ... on CustomMetadataValues {{ values }}
  }}
  ... on File {{ filename size extension fileCreatedAt previewUrl thumbnailUrl downloadUrl }}
  ... on Image {{ filename size extension fileCreatedAt previewUrl thumbnailUrl downloadUrl width height }}
  ... on Document {{ filename size extension fileCreatedAt previewUrl thumbnailUrl downloadUrl width height pageCount }}
  ... on Video {{ filename size extension fileCreatedAt previewUrl thumbnailUrl downloadUrl width height duration bitrate }}
  ... on Audio {{ filename size extension fileCreatedAt previewUrl thumbnailUrl downloadUrl }}
"""

ASSET_FIELDS_CORE = """
  __typename id title description createdAt modifiedAt author status
  ... on File { filename size extension fileCreatedAt downloadUrl }
  ... on Image { filename size extension fileCreatedAt downloadUrl width height }
  ... on Document { filename size extension fileCreatedAt downloadUrl }
  ... on Video { filename size extension fileCreatedAt downloadUrl }
  ... on Audio { filename size extension fileCreatedAt downloadUrl }
"""

ASSET_LEVELS = [ASSET_FIELDS_FULL, ASSET_FIELDS_CORE]

FOLDER_FIELDS = "id name createdAt modifiedAt"


def _root(kind: str) -> tuple[str, str]:
    """(graphql root selection prefix, path list head)."""
    if kind == "library":
        return "library(id: $id) { browse {", "library"
    if kind == "workspace":
        return "workspaceProject(id: $id) { browse {", "workspaceProject"
    raise ValueError(kind)


def folders_query(kind: str) -> tuple[str, list[str]]:
    """Folders directly under a library/workspace root or under a folder id."""
    if kind == "folder":
        q = f"""query FolderChildren($id: ID!, $page: Int!, $limit: Int!) {{
          node(id: $id) {{ ... on SubFolder {{ folders(page: $page, limit: $limit) {{
            total hasNextPage items {{ {FOLDER_FIELDS} }} }} }} }} }}"""
        return q, ["node", "folders"]
    head, root = _root(kind)
    q = f"""query RootFolders($id: ID!, $page: Int!, $limit: Int!) {{
      {head} folders(page: $page, limit: $limit) {{ total hasNextPage items {{ {FOLDER_FIELDS} }} }} }} }} }}"""
    return q, [root, "browse", "folders"]


def assets_query(kind: str, level: int = 0) -> tuple[str, list[str]]:
    fields = ASSET_LEVELS[level]
    if kind == "folder":
        q = f"""query FolderAssets($id: ID!, $page: Int!, $limit: Int!) {{
          node(id: $id) {{ ... on SubFolder {{ assets(page: $page, limit: $limit) {{
            total hasNextPage items {{ {fields} }} }} }} }} }}"""
        return q, ["node", "assets"]
    head, root = _root(kind)
    q = f"""query RootAssets($id: ID!, $page: Int!, $limit: Int!) {{
      {head} assets(page: $page, limit: $limit) {{ total hasNextPage items {{ {fields} }} }} }} }} }}"""
    return q, [root, "browse", "assets"]


def container_total_query(kind: str) -> tuple[str, list[str]]:
    """``assets.total`` of the whole library/workspace: cross-check for the folder crawl."""
    root = "library" if kind == "library" else "workspaceProject"
    return (
        f"query ContainerTotal($id: ID!) {{ {root}(id: $id) {{ assets(limit: 1, page: 1) {{ total }} }} }}",
        [root, "assets"],
    )


LIBRARY_COLLECTIONS = """query LibraryCollections($id: ID!, $page: Int!, $limit: Int!) {
  library(id: $id) { collections(page: $page, limit: $limit) { total hasNextPage items { id name } } } }"""

COLLECTION_ASSETS = """query CollectionAssets($id: ID!, $page: Int!, $limit: Int!) {
  node(id: $id) { ... on Collection { assets(page: $page, limit: $limit) { total hasNextPage items { id } } } } }"""

ASSETS_BY_IDS_DOWNLOAD = """query AssetDownloadUrls($ids: [ID!]!) {
  assets(ids: $ids) { id
    ... on File { downloadUrl } ... on Image { downloadUrl } ... on Document { downloadUrl }
    ... on Video { downloadUrl } ... on Audio { downloadUrl } } }"""

ASSETS_RELATED = """query AssetRelated($ids: [ID!]!) {
  assets(ids: $ids) { id relatedAssets(limit: 100, page: 1) { total items { id } } } }"""

# ------------------------------------------------------------------ guidelines
BRAND_GUIDELINES = """query BrandGuidelines($id: ID!, $page: Int!, $limit: Int!) {
  brand(id: $id) { guidelines(page: $page, limit: $limit) { total hasNextPage items { id name url } } } }"""

_TOP_NAV = """
  __typename
  ... on GuidelineCoverPageNavigationItem { id title url }
  ... on GuidelineDocumentNavigationItem { id title url isHiddenInNavigation }
  ... on GuidelineDocumentGroupNavigationItem { id title isHiddenInNavigation }
  ... on GuidelineDocumentLibraryNavigationItem { id title url isHiddenInNavigation libraryType }
  ... on GuidelineDocumentLinkNavigationItem { id title url openNewTab }
"""

GUIDELINE_NAV = f"""query GuidelineNav($id: ID!, $page: Int!, $limit: Int!) {{
  node(id: $id) {{ ... on Guideline {{ navigation(page: $page, limit: $limit) {{
    total hasNextPage items {{ {_TOP_NAV} }} }} }} }} }}"""

_PAGE_LEAF = """
  __typename
  ... on GuidelineDocumentPageNavigationItem { id title url isHiddenInNavigation isPublished }
  ... on GuidelineDocumentPageLinkNavigationItem { id title url openNewTab }
"""
_CAT = """
  ... on GuidelineDocumentPageCategoryNavigationItem { id title url }
"""
_GROUP_CHILD = """
  __typename
  ... on GuidelineDocumentNavigationItem { id title url isHiddenInNavigation }
  ... on GuidelineDocumentLibraryNavigationItem { id title url isHiddenInNavigation libraryType }
  ... on GuidelineDocumentLinkNavigationItem { id title url openNewTab }
"""

NAV_CHILDREN = f"""query NavChildren($id: ID!, $page: Int!, $limit: Int!) {{
  guidelineNavigationItem(id: $id) {{
    __typename
    ... on GuidelineDocumentNavigationItem {{ docChildren: children(page: $page, limit: $limit) {{
      total hasNextPage items {{ {_PAGE_LEAF} {_CAT} }} }} }}
    ... on GuidelineDocumentGroupNavigationItem {{ groupChildren: children(page: $page, limit: $limit) {{
      total hasNextPage items {{ {_GROUP_CHILD} }} }} }}
    ... on GuidelineDocumentPageCategoryNavigationItem {{ catChildren: children(page: $page, limit: $limit) {{
      total hasNextPage items {{ {_PAGE_LEAF} }} }} }}
  }} }}"""

_BLOCK = """
  id url modifiedAt content settings type { id name }
"""
_BLOCK_ASSETS = """
  assetSettings(limit: 100, page: 1) { total items { settingName assets(limit: 100, page: 1) { total items { previewUrl } } } }
"""


def guideline_page_query(with_assets: bool = True) -> str:
    extra = _BLOCK_ASSETS if with_assets else ""
    return f"""query GuidelinePageContent($id: ID!, $page: Int!, $limit: Int!, $elementsPage: Int!) {{
  guidelinePage(id: $id) {{ id title url modifiedAt
    sections(page: $page, limit: $limit) {{ total hasNextPage items {{ id
      elements(page: $elementsPage, limit: 100) {{ total hasNextPage items {{
        __typename
        ... on GuidelinePageHeading {{ id title url modifiedAt }}
        ... on GuidelinePageBlockInterface {{ {_BLOCK} {extra} }}
        ... on GuidelinePageBlockReference {{ id block {{ __typename ... on GuidelinePageBlockInterface {{ {_BLOCK} }} }} }}
      }} }}
    }} }}
  }} }}"""


LIBRARY_PAGE_ASSETS = """query LibraryPageAssets($id: ID!, $page: Int!, $limit: Int!) {
  node(id: $id) { ... on LibraryPage { assets(page: $page, limit: $limit) { total hasNextPage items { id } } } } }"""

BRAND_ESSENTIALS = """query BrandEssentials($id: ID!) {
  brand(id: $id) { essentials {
    colorPalettes(limit: 100, page: 1) { total hasNextPage items { id name description
      colors(limit: 100, page: 1) { total hasNextPage items { id name description
        representations { hex { name value } pantone { name value } pantoneCoated { name value }
                          pantoneUncoated { name value } } } } } }
    fontFamilies(limit: 100, page: 1) { total hasNextPage items { id name cssName provider
      fontStyles { name weight isItalic } } }
  } } }"""

BRAND_METADATA_PROPS = """query BrandCustomMetadata($id: ID!) {
  brand(id: $id) { customMetadataProperties { id name helpText isRequired } } }"""
