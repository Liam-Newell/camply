"""
``FilteredCampingSearch`` — wraps any ``BaseCampingSearch`` and applies
a :class:`~camply.extensions.canada_filters.pipeline.FilterPipeline` to
the campsites it returns.

The wrapper is a thin proxy: every attribute access not handled
locally is forwarded to the wrapped search instance. The only methods
overridden are the two that produce the user-facing list of
``AvailableCampsite``:

* ``_search_matching_campsites_available`` — called every polling
  cycle by the ``tenacity`` retryer. Re-raises ``CampsiteNotFoundError``
  when the filter pipeline empties the result so that
  ``--search-forever`` / ``--continuous`` keep polling.
* ``get_matching_campsites`` — the public single-shot entry point.

Because the wrapper does not subclass any provider-specific search
class, it works uniformly with ``GoingToCamp``, ``RecreationDotGov``,
``UseDirect`` or any future ``BaseCampingSearch``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from camply.containers import AvailableCampsite
from camply.exceptions import CampsiteNotFoundError
from camply.search.base_search import BaseCampingSearch

from camply.extensions.canada_filters.pipeline import FilterPipeline

logger = logging.getLogger(__name__)


class FilteredCampingSearch:
    """
    Post-filter middleware around a :class:`BaseCampingSearch`.

    Parameters
    ----------
    wrapped : BaseCampingSearch
        An already-constructed concrete camply search instance.
    pipeline : FilterPipeline
        Pipeline applied to the campsites returned by ``wrapped``.
    """

    def __init__(
        self, wrapped: BaseCampingSearch, pipeline: FilterPipeline
    ) -> None:
        self._wrapped = wrapped
        self._pipeline = pipeline
        # Patch the inner method called by the continuous-search retry
        # loop so that filtered-out results trigger another poll
        # instead of returning an empty list.
        self._original_inner = wrapped._search_matching_campsites_available
        wrapped._search_matching_campsites_available = (  # type: ignore[method-assign]
            self._filtered_inner_search
        )

    # ------------------------------------------------------------------
    # Proxying
    # ------------------------------------------------------------------
    def __getattr__(self, item):
        # ``__getattr__`` is only called when normal lookup fails, so
        # this safely forwards everything we don't override.
        return getattr(self._wrapped, item)

    @property
    def wrapped(self) -> BaseCampingSearch:
        """The underlying search instance."""
        return self._wrapped

    @property
    def pipeline(self) -> FilterPipeline:
        """The configured filter pipeline."""
        return self._pipeline

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def apply_filters(
        self, campsites: List[AvailableCampsite]
    ) -> List[AvailableCampsite]:
        """Apply the pipeline to ``campsites`` and return the result."""
        if not self._pipeline:
            return list(campsites)
        before = len(campsites)
        filtered = self._pipeline(campsites)
        logger.info(
            "canada_filters: %d campsite(s) before filtering, %d after.",
            before,
            len(filtered),
        )
        return filtered

    def _filtered_inner_search(
        self,
        log: bool = False,
        verbose: bool = False,
        raise_error: bool = False,
    ) -> List[AvailableCampsite]:
        """
        Replacement for ``BaseCampingSearch._search_matching_campsites_available``.

        Runs the wrapped search's original implementation, applies the
        filter pipeline, and re-raises ``CampsiteNotFoundError`` when
        the filtered result is empty (so the existing tenacity retryer
        keeps polling under ``--search-forever`` / ``--continuous``).
        """
        raw_results = self._original_inner(
            log=False, verbose=False, raise_error=raise_error
        )
        filtered = self.apply_filters(raw_results)
        # Keep the wrapper's notion of "found" in sync with what the
        # user actually wants to be notified about so that
        # ``search-forever`` deduplication works on the filtered set.
        try:
            found = getattr(self._wrapped, "campsites_found", None)
            if isinstance(found, set):
                removed = {site for site in raw_results if site not in filtered}
                found.difference_update(removed)
        except (AttributeError, TypeError):  # defensive; never break the search
            logger.debug(
                "Could not sync campsites_found after filtering", exc_info=True
            )
        if not filtered and raise_error:
            raise CampsiteNotFoundError(
                "No campsites passed the canada_filters pipeline — "
                "we'll continue checking"
            )
        if log and filtered:
            # Delegate logging/notification assembly to the wrapped
            # search so output formatting is unchanged.
            self._wrapped.assemble_availabilities(
                matching_data=filtered, log=log, verbose=verbose
            )
        return filtered

    def get_matching_campsites(
        self,
        log: bool = True,
        verbose: bool = False,
        continuous: bool = True,
        polling_interval: Optional[int] = None,
        notify_first_try: Optional[bool] = None,
        notification_provider: Optional[object] = None,
        search_forever: Optional[bool] = None,
        search_once: bool = False,
    ) -> List[AvailableCampsite]:
        """
        Run the wrapped search end-to-end. The pipeline is applied on
        every polling cycle via :meth:`_filtered_inner_search`.
        """
        return self._wrapped.get_matching_campsites(
            log=log,
            verbose=verbose,
            continuous=continuous,
            polling_interval=polling_interval,
            notify_first_try=notify_first_try,
            notification_provider=notification_provider,
            search_forever=search_forever,
            search_once=search_once,
        )
