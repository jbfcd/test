import sys
from typing import Any
from typing import cast
from typing import Iterable
from typing import Iterator
from typing import NamedTuple
from typing import TYPE_CHECKING

import docutils.nodes
import sphinx.builders.dummy
import sphinx.transforms.post_transforms
import sphinx.util.logging
import sphinx.util.nodes


if TYPE_CHECKING:
    import sphinx.application
    import sphinx.domains

if sys.version_info >= (3, 9):
    Inventory = dict[str, dict[str, tuple[str, str, str, str]]]
else:
    from typing import Dict, Tuple

    Inventory = Dict[str, Dict[str, Tuple[str, str, str, str]]]


logger = sphinx.util.logging.getLogger(__name__)


class URIInfo(NamedTuple):
    uri: str
    document_name: str
    line_number: int


class LinkCollector(sphinx.transforms.post_transforms.SphinxPostTransform):
    """
    Traverse the document and collect all ``reference`` nodes that do not have the ``internal`` attribute set.

    Typically, they will look like this:

    .. code-block::

       <reference name="link text" refuri="https://uri">link text, maybe further styled</reference>

    We know those were not generated by Sphinx because they are missing the ``internal`` attribute.

    This transform doesn't actually modify the document tree, only collecting stuff.
    """

    builders = ("crossrefcheck",)
    default_priority = 900

    def run(self, **kwargs: Any) -> None:
        builder = cast(ExternalLinkChecker, self.app.builder)

        for refnode in self.document.traverse(docutils.nodes.reference):
            if "internal" in refnode or "refuri" not in refnode:
                continue
            uri = refnode["refuri"]
            lineno = sphinx.util.nodes.get_node_line(refnode)

            uri_info = URIInfo(uri, self.env.docname, lineno)
            builder.uris.append(uri_info)


class ExternalLinkChecker(sphinx.builders.dummy.DummyBuilder):
    """
    Custom builder that does not build anything, only analyzes the built result.

    It is invoked when the user selects ``crossrefcheck`` as builder name
    in the terminal:

    .. code-block:: sh

       $ sphinx-build -b crossrefcheck doc/en/ build

    For every link not generated by Sphinx, it compares whether it matches
    an inventory URL configured in ``intersphinx_mapping`` and warns if the
    link can be replaced by an cross-reference.

    .. note:: The matching is done by simply comparing URLs as strings
       via ``str.startswith``. This means that with e.g. ``x`` project
       configured as

       .. code-block:: python

          intersphinx_mapping = {
              "x": ("https://x.readthedocs.io/en/stable", None),
          }

       no warning will be emitted for links ``https://x.readthedocs.io/en/latest``
       or ``https://x.readthedocs.io/de/stable``.

       Those links can be included by adding the missing docs
       for ``x`` to ``intersphinx_mapping``:

       .. code-block:: python

          intersphinx_mapping = {
              "x": ("https://x.readthedocs.io/en/stable", None),
              "x-dev": ("https://x.readthedocs.io/en/latest", None),
              "x-german": ("https://x.readthedocs.io/de/stable", None),
          }

    """

    name = "crossrefcheck"

    def __init__(self, app: "sphinx.application.Sphinx") -> None:
        super().__init__(app)
        self.uris: list[URIInfo] = []

    def finish(self) -> None:
        intersphinx_cache = getattr(self.app.env, "intersphinx_cache", dict())
        for uri_info in self.uris:
            for inventory_uri, (
                inventory_name,
                _,
                inventory,
            ) in intersphinx_cache.items():
                if uri_info.uri.startswith(inventory_uri):
                    # build a replacement suggestion
                    try:
                        replacement = next(
                            replacements(
                                uri_info.uri, inventory, self.app.env.domains.values()
                            )
                        )
                        suggestion = f"try using {replacement!r} instead"
                    except StopIteration:
                        suggestion = "no suggestion"

                    location = (uri_info.document_name, uri_info.line_number)
                    logger.warning(
                        "hardcoded link %r could be replaced by a cross-reference to %r inventory (%s)",
                        uri_info.uri,
                        inventory_name,
                        suggestion,
                        location=location,
                    )


def replacements(
    uri: str, inventory: Inventory, domains: Iterable["sphinx.domains.Domain"]
) -> Iterator[str]:
    """
    Create a crossreference to replace hardcoded ``uri``.

    This is straightforward: search the given inventory
    for an entry that points to the ``uri`` and build
    a ReST markup that should replace ``uri`` with a crossref.
    """
    for key, entries in inventory.items():
        domain_name, directive_type = key.split(":")
        for target, (_, _, target_uri, _) in entries.items():
            if uri == target_uri:
                role = "any"
                for domain in domains:
                    if domain_name == domain.name:
                        role = domain.role_for_objtype(directive_type) or "any"
                        yield f":{domain_name}:{role}:`{target}`"


def setup(app: "sphinx.application.Sphinx") -> None:
    """Register this extension."""
    app.add_builder(ExternalLinkChecker)
    app.add_post_transform(LinkCollector)
