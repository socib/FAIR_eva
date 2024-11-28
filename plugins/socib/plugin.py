#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import logging
import sys
import re
import requests
from dateutil.parser import isoparse
import api.utils as ut
from bs4 import BeautifulSoup as bs

import pandas as pd

from api.evaluator import ConfigTerms, Evaluator
from api.vocabulary import Vocabulary

logging.basicConfig(
    stream=sys.stdout, level=logging.DEBUG, format="'%(name)s:%(lineno)s' | %(message)s"
)

logger = logging.getLogger("api.plugin")
logger_api = logging.getLogger("api.plugin")

from api.evaluator import Evaluator, MetadataValuesBase

class MetadataValues(MetadataValuesBase):

    @classmethod
    def gather(cls, element_values, element):
        """Gets the metadata value according to the given element.

        It calls the appropriate class method.
        TODO: Avoid duplication code either by udating this method in the parent class (to include the new casuistic), or by rewriting
        the superclass method to avoid duplicing the code that manages the exception handling. 
        """
        _values = []
        try:
            if element == "Metadata Identifier":
                _values = cls._get_identifiers_metadata(element_values)
            elif element == "Data Identifier":
                _values = cls._get_identifiers_data(element_values)
            elif element == "Temporal Coverage":
                _values = cls._get_temporal_coverage(element_values)
            elif element == "Person Identifier":
                _values = cls._get_person(element_values)
            elif element == "Date":
                _values = cls._get_date(element_values)
            else:
                raise NotImplementedError("Self-invoking NotImplementedError exception")
        except Exception as e:
            logger_api.exception(str(e))
            _values = element_values
            if isinstance(element_values, str):
                _values = [element_values]
            logger_api.warning(
                "No specific plugin's gather method defined for metadata element '%s'. Returning input values formatted to list: %s"
                % (element, _values)
            )
        else:
            logger_api.debug(
                "Successful call to plugin's gather method for the metadata element '%s'. Returning: %s"
                % (element, _values)
            )
        finally:
            return _values

    @classmethod
    def _get_identifiers_metadata(cls, element_values):
        """Get the list of identifiers for the metadata.

        * Format EPOS DEV API:
            "id": "77c89ce5-cbaa-4ea8-bcae-fdb1da932f6e"
        """
        return element_values

    @classmethod
    def _get_identifiers_data(cls, element_values):
        """Get the list of identifiers for the data.

        * Format EPOS DEV API:
            "identifiers": [{
                "type": "DOI",
                "value": "https://doi.org/10.13127/tsunami/neamthm18"
            }]
        """
        return [value_data["value"] for value_data in element_values]

    @classmethod
    def _get_temporal_coverage(cls, element_values):
        """Return a list of tuples with temporal coverages for start and end date.

        * Format EPOS PROD & DEV API:
            "temporalCoverage": [{
                "startDate": "2018-01-31T00:00:00Z"
            }]
        """
        return [
            (value_data.get("startDate", ""), value_data.get("endDate", ""))
            for value_data in element_values
        ]

    @classmethod
    def _get_person(cls, element_values):
        """Return a list with person-related info.

        * Format SOCIB Data API:
            "contactPoints": [{ TO BE UPDATED
              "id": "8069667d-7676-4c02-b98e-b1e044ab4cd7",
              "metaid": "2870c8e4-c616-4eaf-b84d-502f6a3ee2fb",
              "uid": "http://orcid.org/0000-0003-4551-3339/Contact"
            }]
        """
        person_data = [
            value_data["@id"]
            for value_data in element_values
            if "@id" in value_data
        ]

        return person_data
    
    @classmethod
    def _get_date(cls, element_values):
        """
        Return a list of dates according to ISO-8601
        """
        date_data = []
        for date in element_values:
            try:
                isoparse(date)
                date_data.append(date)
            except ValueError as e:
                # Not a valid date: do nothing as this is not a validation step
                continue

        return date_data
        
    def _validate_license(self, licenses, vocabularies, machine_readable=False):
        license_data = {}
        for vocabulary_id, vocabulary_url in vocabularies.items():
            # Store successfully validated licenses, grouped by CV
            license_data[vocabulary_id] = {"valid": [], "non_valid": []}
            # SPDX
            if vocabulary_id in ["spdx"]:
                logger_api.debug(
                    "Validating licenses according to SPDX vocabulary: %s" % licenses
                )
                for _license in licenses:
                    if ut.is_spdx_license(_license, machine_readable=machine_readable):
                        logger.debug(
                            "License successfully validated according to SPDX vocabulary: %s"
                            % _license
                        )
                        license_data[vocabulary_id]["valid"].append(_license)
                    else:
                        logger.warning(
                            "Could not find any license match in SPDX vocabulary for '%s'"
                            % _license
                        )
                        license_data[vocabulary_id]["non_valid"].append(_license)
            else:
                logger.warning(
                    "Validation of vocabulary '%s' not yet implemented" % vocabulary_id
                )

        return license_data



class Plugin(Evaluator):
    """A class used to define FAIR indicators tests. It contains all the references to
    all the tests. This is an example to be tailored to what your needs.

    Attributes
    ----------
    item_id : str
        Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an identifier from the repo)
    oai_base : str
        Open Archives initiative , This is the place in which the API will ask for the metadata
    lang : Language
    """
    def __init__(self, item_id, oai_base=None, lang="en", config=None):
        plugin = "socib"
        super().__init__(item_id, oai_base, lang, plugin, config)
        # TO REDEFINE - WHICH IS YOUR PID TYPE?
        self.id_type = "internal"
        self.vocabulary = Vocabulary(config)

        global _
        _ = super().translation()

        self.base_url = ast.literal_eval(self.config[plugin]["base_url"])

        # You need a way to get your metadata in a similar format
        metadata_sample = self.get_metadata()
        # self.metadata = pd.json_normalize(metadata_sample)
        self.metadata = pd.DataFrame(
            metadata_sample,
            columns=["metadata_schema", "element", "text_value", "qualifier"],
        )

        logger.debug("METADATA: %s" % (self.metadata))
        # Protocol for (meta)data accessing
        if len(self.metadata) > 0:
            self.access_protocols = ["http"]

        # Config attributes
        self.version = ast.literal_eval(self.config[self.name]["version"])
        self.terms_map = ast.literal_eval(self.config[self.name]["terms_map"])

        self.identifier_term = ast.literal_eval(self.config[plugin]["identifier_term"])
        self.terms_quali_generic = ast.literal_eval(
            self.config[plugin]["terms_quali_generic"]
        )
        self.terms_quali_disciplinar = ast.literal_eval(
            self.config[plugin]["terms_quali_disciplinar"]
        )
        self.terms_access = ast.literal_eval(self.config[plugin]["terms_access"])
        self.terms_cv = ast.literal_eval(self.config[plugin]["terms_cv"])
        self.supported_data_formats = ast.literal_eval(
            self.config[plugin]["supported_data_formats"]
        )
        self.terms_qualified_references = ast.literal_eval(
            self.config[plugin]["terms_qualified_references"]
        )
        self.terms_relations = ast.literal_eval(self.config[plugin]["terms_relations"])
        self.terms_license = ast.literal_eval(self.config[plugin]["terms_license"])
        self.metadata_schemas = ast.literal_eval(
            self.config[plugin]["metadata_schemas"]
        )
        self.metadata_quality = 100  # Value for metadata balancing
        
        # This a custom field for SOCIB Data Repository
        self.data_standard = ast.literal_eval(self.config[plugin]["data_standard"])

    @property
    def metadata_utils(self):
        return MetadataValues()

    def get_metadata(self):
        # Step 1: obtain data product slug from DataCite Fabrica REST API
        datacite_api_url = self.item_id.replace("doi.org", "api.datacite.org/dois")

        logging.debug("Connecting to the DataCite Fabrica REST API: %s" % datacite_api_url)
        response = requests.get(datacite_api_url)

        if not response.ok:
            msg = "Error while connecting to the DataCite Fabrica REST API: %s" % (datacite_api_url, response.status_code)
            logging.error(msg)
            raise Exception(msg)
        
        response_dict = response.json()

        doi_url = response_dict["data"]["attributes"]["url"]
        index = doi_url.find("/data-catalog/") + len("/data-catalog/") 
        data_product_slug = doi_url[index:]

        # Step 2: access metadata expressed in JSON-LD and schema.org: from the SOCIB API
        socib_api_url = (
            self.base_url + "/data-products/" + data_product_slug + "/metadata"
        )
        headers = {
            "api_key": self.config[self.name]["socib_api_key"]
        }

        logging.debug("Connecting to the SOCIB REST API: %s" % socib_api_url)
        response = requests.get(
            socib_api_url,
            headers=headers,
        )
        if not response.ok:
            msg = (
                "Error while connecting to metadata repository: %s (status code: %s)"
                % (response.url, response.status_code)
            )
            logging.error(msg)
            raise Exception(msg)

        # Storing headers
        self.metadata_endpoint_headers = response.headers
        logger.debug(
            "Storing headers from metadata repository: %s"
            % self.metadata_endpoint_headers
        )

        # Step 3: processing returned metadata as part of the FAIR Eva dataflow 
        dicion = response.json()

        metadata_schema = dicion['json_ld']['schemaVersion']
        
        eml_schema = metadata_schema
        metadata = []
        dicion = dicion['json_ld']
        for key in dicion.keys():
            value = dicion[key]
            if str(type(value)) == "<class 'list'>":
                for element in value:
                    metadata.append([eml_schema, key, element, None])
            else:
                metadata.append([eml_schema, key, dicion[key], None])

        return metadata

    def rda_f4_01m(self):
        """Indicator RDA-F4-01M: Metadata is offered in such a way that it can be harvested and indexed.

        This indicator is linked to the following principle: F4: (Meta)data are registered or indexed
        in a searchable resource.

        The indicator tests whether the metadata is offered in such a way that it can be indexed.
        In some cases, metadata could be provided together with the data to a local institutional
        repository or to a domain-specific or regional portal, or metadata could be included in a
        landing page where it can be harvested by a search engine. The indicator remains broad
        enough on purpose not to  limit the way how and by whom the harvesting and indexing of
        the data might be done.

        Returns
        -------
        points
            - 100 if metadata could be gathered using any of the supported protocols (OAI-PMH, HTTP).
            - 0 otherwise.
        msg
            Message with the results or recommendations to improve this indicator
        """
        msg_list = []
        if len(self.metadata) > 0:
            points = 100
            msg = _("Metadata is searchable by Google because of the JSON-LD record included in the landing page")
        else:
            points = 0
            msg = _(
                "No metadata record is included as a JSON-LD object in the data product's landing page. Please, contact to repository data steward"
            )
        msg_list.append({"message": msg, "points": points})

        return (points, msg_list)

    @ConfigTerms(term_id="terms_access")
    def rda_a1_01m(self, **kwargs):
        """Indicator RDA-A1-01M.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol. More information about that
        principle can be found here.

        The indicator refers to the information that is necessary to allow the requester to gain access
        to the digital object. It is (i) about whether there are restrictions to access the data (i.e.
        access to the data may be open, restricted or closed), (ii) the actions to be taken by a
        person who is interested to access the data, in particular when the data has not been
        published on the Web and (iii) specifications that the resources are available through
        eduGAIN7 or through specialised solutions such as proposed for EPOS.

        Returns
        -------
        points
            - 100 if access metadata is available and data can be access manually
            - 0 otherwise
        msg
            Message with the results or recommendations to improve this indicator
        """
        # 1 - Check metadata record for access info
        msg_list = []
        points = 0

        term_data = kwargs["terms_access"]
        term_metadata = term_data["metadata"]

        msg_st_list = []
        for index, row in term_metadata.iterrows():
            msg_st_list.append(
                _("Metadata found for access") + ": " + row["text_value"]
            )
            logging.debug(_("Metadata found for access") + ": " + row["text_value"])
            points = 100
        msg_list.append({"message": msg_st_list, "points": points})

        # 2 - Data is only downloadable upon registration in the SOCIB website
        msg_2 = "Data is only downloadable upon registration in the SOCIB website"
        points_2 = 100

        if points_2 == 100 and points == 100:
            msg_list.append(
                {
                    "message": _("Data can be accessed manually") + " | %s" % msg_2,
                    "points": points_2,
                }
            )
        elif points_2 == 0 and points == 100:
            msg_list.append(
                {
                    "message": _("Data can not be accessed manually") + " | %s" % msg_2,
                    "points": points_2,
                }
            )
        elif points_2 == 100 and points == 0:
            msg_list.append(
                {
                    "message": _("Data can be accessed manually") + " | %s" % msg_2,
                    "points": points_2,
                }
            )
            points = 100
        elif points_2 == 0 and points == 0:
            msg_list.append(
                {
                    "message": _(
                        "No access information can be found in the metadata. Please, add information to the following term(s)"
                    )
                    + " %s" % term_data,
                    "points": points_2,
                }
            )

        return (points, msg_list)

    def rda_a1_02m(self):
        """Indicator RDA-A1-02M
        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol.

        The indicator refers to any human interactions that are needed if the requester wants to
        access metadata. The FAIR principle refers mostly to automated interactions where a
        machine is able to access the metadata, but there may also be metadata that require human
        interactions. This may be important in cases where the metadata itself contains sensitive
        information. Human interaction might involve sending an e-mail to the metadata owner, or
        calling by telephone to receive instructions.

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        # Look for the metadata terms in HTML in order to know if they can be accessed manually
        try:
            response = requests.get(self.item_id, allow_redirects=True)
            soup = bs(response.text, features="html.parser")
            
            json_ld_tags = soup.findAll("script", {"type": "application/ld+json"})
            if len(json_ld_tags) > 0:
                points = 100
                msg = "JSON-LD available in the landing page. Javascript takes care of formatting it for human readability"
            else:
                points = 0
                msg = "No JSON-LD avaialble in the landing page"
        except Exception as e:
            logger.error(e)

        return (points, [{"message": msg, "points": points}])

    def rda_a1_03m(self):
        """Indicator RDA-A1-03M Metadata identifier resolves to a metadata record.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol.

        This indicator is about the resolution of the metadata identifier. The identifier assigned to
        the metadata should be associated with a resolution service that enables access to the
        metadata record.

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """        
        points = 0
        msg = (
            "Metadata record cannot be retrieved from metadata identifier: %s"
            % self.item_id
        )
        if not self.metadata.empty:
            points = 100 # We considered that the metadata field being not empty, is equivalent to meet this requirement 100%
                        # as the metadata has been recovered in the initialization of this instance.
            msg = (
                "Metadata record could be retrieved from metadata identifier: %s"
                % self.item_id
            )

        msg_list = [{"message": msg, "points": points}]

        return (points, msg_list)
    

    def rda_a1_03d(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol. More information about that
        principle can be found here.
        This indicator is about the resolution of the identifier that identifies the digital object. The
        identifier assigned to the data should be associated with a formally defined
        retrieval/resolution mechanism that enables access to the digital object, or provides access
        instructions for access in the case of human-mediated access. The FAIR principle and this
        indicator do not say anything about the mutability or immutability of the digital object that
        is identified by the data identifier -- this is an aspect that should be governed by a
        persistence policy of the data provider
        Technical proposal:
        Parameters
        ----------
        item_id : str
            Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)
        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        
        Note: This asessment is tied to SOCIB use case in witch the link to the digital object is provided
        solely if the user sign in the SOCIB website
        """

        msg_list = []
        points = 100
        
        msg_list.append(
            {
                "message": "Data can be downloaded upon registration in the SOCIB website",
                "points": 100,
            }
        )

        return points, msg_list

    def rda_a1_04m(self, return_protocol=False):
        """Indicator RDA-A1-04M: Metadata is accessed through standarised protocol.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol.

        The indicator concerns the protocol through which the metadata is accessed and requires
        the protocol to be defined in a standard.

        Returns
        -------
        points
            100/100 if the endpoint protocol is in the accepted list of standarised protocols
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0

        protocol = ut.get_protocol_scheme(self.item_id)
        if protocol in self.terms_access_protocols:
            points = 100
            msg = "Found a standarised protocol to access the metadata record: " + str(
                protocol
            )
        else:
            msg = (
                "Found a non-standarised protocol to access the metadata record: %s"
                % str(protocol)
            )
        msg_list = [{"message": msg, "points": points}]

        if return_protocol:
            return (points, msg_list, protocol)
        
        return (points, msg_list)

    def rda_a1_05d(self):
        """Indicator RDA-A1-01M.

        This indicator is linked to the following principle: A1: (Meta)data are retrievable by their
        identifier using a standardised communication protocol. More information about that
        principle can be found here.

        The indicator refers to automated interactions between machines to access digital objects.
        The way machines interact and grant access to the digital object will be evaluated by the
        indicator.

        Returns
        -------
        points
            0 since SOCIB does not support machine actionable access to data
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0
        msg_list = []
        msg_list.append(
            {
                "message": _(
                    "SOCIB Data Repository does not support machine-actionable access to data from their persistent identifier (ie. DOI)"
                ),
                "points": points,
            }
        )

        return points, msg_list
    
    def rda_a1_2_01d(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: A1.2: The protocol allows for an
        authentication and authorisation where necessary. More information about that principle
        can be found here.
        The indicator requires the way that access to the digital object can be authenticated and
        authorised and that data accessibility is specifically described and adequately documented.
        Technical proposal:
        Parameters
        ----------
        item_id : str
            Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)
        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 100
        msg_list = []
        msg_list.append(
            {
                "message": _(
                    "SOCIB implemets AAI to access the digital object"
                ),
                "points": points,
            }
        )
        return points, msg_list
    
    def rda_a2_01m(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: A2: Metadata should be accessible even
        when the data is no longer available. More information about that principle can be found
        here.
        The indicator intends to verify that information about a digital object is still available after
        the object has been deleted or otherwise has been lost. If possible, the metadata that
        remains available should also indicate why the object is no longer available.
        Technical proposal:
        Parameters
        ----------
        item_id : str
            Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)
        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 100 
        msg = _(
            "SOCIB Data Repository Preservation Plan policy is available at: https://repository.socib.es/repository/entry/show?entryid=504dd999-0e5e-49c0-b2e1-790559055fd0"
        )
        return points, [{"message": msg, "points": points}]

    @ConfigTerms(term_id="terms_cv", validate=True)
    def rda_i1_01m(self, **kwargs):
        """Indicator RDA-I1-01M: Metadata uses knowledge representation expressed in standarised format.

        This indicator is linked to the following principle: I1: (Meta)data use a formal,
        accessible, shared, and broadly applicable language for knowledge representation.

        The indicator serves to determine that an appropriate standard is used to express
        knowledge, for example, controlled vocabularies for subject classifications.

        Returns
        -------
        points
            Points are proportional to the number of followed vocabularies

        msg
            Message with the results or recommendations to improve this indicator
        """
        (_msg, _points) = self.eval_validated_basic(kwargs)

        return (_points, [{"message": _msg, "points": _points}])
    
    def rda_i1_01d(self, **kwargs):
        """Indicator RDA-I1-01D: Data uses knowledge representation expressed in standarised format.

        This indicator is linked to the following principle: I1: (Meta)data use a formal,
        accessible, shared, and broadly applicable language for knowledge representation.

        The indicator serves to determine that an appropriate standard is used to express
        knowledge, in particular the data model and format.

        Returns
        -------
        points
            100/100 If the file format is listed under IANA Internet Media Types
        msg
            Message with the results or recommendations to improve this indicator
        """
        data_standards = self.data_standard

        elements_using_vocabulary = []
        for data_standard in data_standards:
            result = self.vocabulary.get_fairsharing(data_standard)
            result_filtered = [item for item in result if item["attributes"]["abbreviation"] == data_standard]
            if result_filtered:
                elements_using_vocabulary.append(data_standard)
            else:    
                logger.warning(
                    "Data standard '%s' not found under FAIRsharing registry"
                    % data_standard
                )

        _msg = (
            "Found %s (%s) out of %s (%s) data standards using standard vocabularies"
            % (
                len(elements_using_vocabulary),
                ", ".join(elements_using_vocabulary),
                len(data_standards),
                ", ".join(data_standards)
            )
        )
        logger.info(_msg)

        # Get scores
        _points = 0
        if data_standards:
            _points = len(elements_using_vocabulary) / len(data_standards) * 100

        return (_points, [{"message": _msg, "points": _points}])
    
    def rda_i1_02m(self, **kwargs):
        """Indicator RDA-I1-02M: Metadata uses machine-understandable knowledge representation.

        This indicator is linked to the following principle: I1: (Meta)data use a formal, accessible,
        shared, and broadly applicable language for knowledge representation. M

        This indicator focuses on the machine-understandability aspect of the data. This means that
        data should be readable and thus interoperable for machines without any requirements such
        as specific translators or mappings.

        Returns
        -------
        points
            - 100/100 if metadata uses machine understandable knowledge representation (0/100 otherwise)
        msg
            Message with the results or recommendations to improve this indicator
        """
        _title = "Metadata uses machine-understandable knowledge representation"
        _checks = {
            "FAIR-EVA-I1-02M-1": {
                "title": "Media type gathered from HTTP headers",
                "critical": True,
                "success": False,
            },
            "FAIR-EVA-I1-02M-2": {
                "title": "Media type listed under IANA Internet Media Types",
                "critical": True,
                "success": False,
            },
        }
        _points = 0

        # FAIR-EVA-I1-02M-1: Get serialization media type from HTTP headers
        content_type = self.metadata_endpoint_headers.get("Content-Type", "")
        if content_type:
            _msg = "Found media type '%s' through HTTP headers" % content_type
            logger.info(_msg)
            _checks["FAIR-EVA-I1-02M-1"].update(
                {
                    "success": True,
                    "points": 100,
                }
            )
        else:
            _msg = (
                "The metadata standard in use does not provide a machine-understandable knowledge expression: %s"
                % self.metadata_standard
            )
            logger.warning(_msg)
        _checks["FAIR-EVA-I1-02M-1"].update(
            {
                "message": _msg,
            }
        )

        # FAIR-EVA-I1-02M-2: Serialization format listed under IANA Media Types
        if content_type in self.vocabulary.get_iana_media_types():
            _msg = (
                "Metadata serialization format '%s' listed under IANA Media Types"
                % content_type
            )
            logger.info(_msg)
            _checks["FAIR-EVA-I1-02M-2"].update(
                {
                    "success": True,
                    "points": 100,
                }
            )
            _points = 100
        else:
            _msg = (
                "Metadata serialization '%s' format is not listed under IANA Internet Media Types"
                % content_type
            )    
            logger.warning(_msg)
        _checks["FAIR-EVA-I1-02M-2"].update(
            {
                "message": _msg,
            }
        )

        return (_points, [{"message": _msg, "points": _points}])

    def rda_i1_02d(self, **kwargs):
        """Indicator RDA-I1-02D: Data uses machine-understandable knowledge representation.

        This indicator is linked to the following principle: I1: (Meta)data use a formal, accessible,
        shared, and broadly applicable language for knowledge representation.

        This indicator focuses on the machine-understandability aspect of the data. This means that
        data should be readable and thus interoperable for machines without any requirements such
        as specific translators or mappings.

        Returns
        -------
        points
            - 100/100 if data models correspond to machine readable formats
            - Otherwise, the resultant score will be proportional to the percentage of machine readable formats
        msg
            Message with the results or recommendations to improve this indicator
        """

        # Overrided to match rda_i1_01d since I don't see the difference.
        (points, msg_list) = self.rda_i1_01d()
        return (points, msg_list)

    @ConfigTerms(term_id="terms_cv")
    def rda_i2_01m(self, **kwargs):
        """Indicator RDA-I2-01D: Data uses FAIR-compliant vocabularies.

        This indicator is linked to the following principle: I2: (Meta)data use vocabularies that follow
        the FAIR principles.

        The indicator requires the controlled vocabulary used for the data to conform to the FAIR
        principles, and at least be documented and resolvable using globally unique.

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """

        # Overrided to match rda_i1_01m since having vocabularies registered in FAIRsharing 
        # can be equivalent to consider them FAIR.
        (points, msg_list) = self.rda_i1_01m()
        return (points, msg_list)
    
    def rda_i2_01d(self):
        """Indicator RDA-A1-01M.

        This indicator is linked to the following principle: I2: (Meta)data use vocabularies that follow
        the FAIR principles. More information about that principle can be found here.

        The indicator requires the controlled vocabulary used for the data to conform to the FAIR
        principles, and at least be documented and resolvable using globally unique

        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        # Overrided to match rda_i1_01d since having vocabularies registered in FAIRsharing 
        # can be equivalent to consider them FAIR.
        (points, msg_list) = self.rda_i1_01d()
        return (points, msg_list)

    def rda_i3_01m(self):
        """Indicator RDA-I3-01M: Metadata includes references to other metadata.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        The indicator is about the way that metadata is connected to other metadata, for example
        through links to information about organisations, people, places, projects or time periods
        that are related to the digital object that the metadata describes.

        Returns
        -------
        points
            100/100 if ORCID is found in the metadata
        msg
            Message with the results or recommendations to improve this indicator
        """
        points, msg = self.rda_i3_03m()

        return (points, msg)
    
    def rda_i3_01d(self):
        """Indicator RDA-I3-01D: Data includes references to other data.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        The indicator is about the way that metadata is connected to other metadata, for example
        through links to information about organisations, people, places, projects or time periods
        that are related to the digital object that the metadata describes.

        Returns
        -------
        points
            Currently returns 0 points, as it requires inspecting the content of the data
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0
        msg = "This test implies checking the presence of qualified references within the content of the data. As it is defined, its implementation is too costly."

        return (points, [{"message": msg, "points": points}])

    def rda_i3_02m(self):
        """Indicator RDA-I3-02M: Metadata includes references to other data.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        This indicator is about the way metadata is connected to other data, for example linking to
        previous or related research data that provides additional context to the data. Please note
        that this is not about the link from the metadata to the data it describes; that link is
        considered in principle F3 and in indicator RDA-F3-01M.

        Returns
        -------
        points
            Returns 100/100 if qualified references are found (0/100 otherwise)
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0
        msg = "No references to other data."

        return (points, [{"message": msg, "points": points}])

    def rda_i3_02d(self):
        """Indicator RDA-I3-02D: Data includes qualified references to other data.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        The indicator is about the way that metadata is connected to other metadata, for example
        through links to information about organisations, people, places, projects or time periods
        that are related to the digital object that the metadata describes.

        Returns
        -------
        points
            Currently returns 0 points, as it requires inspecting the content of the data
        msg
            Message with the results or recommendations to improve this indicator
        """

        points = 0
        msg = "This test implies checking the presence of qualified references within the content of the data. As it is defined, its implementation is too costly."

        return (points, [{"message": msg, "points": points}])

    @ConfigTerms(term_id="terms_relations", validate=True)
    def rda_i3_03m(self, **kwargs):
        """Indicator RDA-I3-03M: Metadata includes qualified references to other metadata.

        This indicator is linked to the following principle: I3: (Meta)data include qualified references
        to other (meta)data. More information about that principle can be found here.

        This indicator is about the way metadata is connected to other metadata, for example to
        descriptions of related resources that provide additional context to the data. The references
        need to be qualified which means that the relation

        Returns
        -------
        points
            100/100 if the ORCID appears in the metadata (ORCID considered a qualified reference to the Author of the file)
        msg
            Message with the results or recommendations to improve this indicator
        """
        has_qualified_references = False
        msg_list = []
        for element, element_data in kwargs.items():
            validation_data = element_data.get("validation", {})
            if validation_data:
                for vocabulary, vocabulary_validation_data in validation_data.items():
                    if vocabulary_validation_data["valid"]:
                        has_qualified_references = True
                        msg_list.append(
                            "'%s' element uses vocabulary %s in '%s'"
                            % (element, vocabulary, vocabulary_validation_data["valid"])
                        )

        if has_qualified_references:
            points = 100
            msg = "Metadata has qualified references to other metadata: %s" % ", ".join(
                msg_list
            )
        else:
            points = 0
            msg = "Metadata does not have qualified references to other metadata"

        return (points, [{"message": msg, "points": points}])

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_02m(self, license_list=[], machine_readable=False, **kwargs):
        """Indicator R1.1-02M: Metadata refers to a standard reuse license.

        This indicator is linked to the following principle: R1.1: (Meta)data are released with a clear
        and accessible data usage license.

        This indicator requires the reference to the conditions of reuse to be a standard licence,
        rather than a locally defined license.

        Returns
        -------
        points
            100/100 if the license is listed under the SPDX licenses
        msg
            Message with the results or recommendations to improve this indicator
        """
        license_list = kwargs["License"]

        points = 0
        max_points = 100

        license_num = len(license_list)
        license_standard_list = []
        points_per_license = round(max_points / license_num)
        for _license in license_list:
            if ut.is_spdx_license(_license, machine_readable=machine_readable):
                license_standard_list.append(_license)
                points += points_per_license
                logger.debug(
                    "License <%s> is considered as standard by SPDX: adding %s points"
                    % (_license, points_per_license)
                )
        if points == 100:
            msg = (
                "License/s in use are considered as standard according to SPDX license list: %s"
                % license_standard_list
            )
        elif points > 0:
            msg = (
                "A subset of the license/s in use (%s out of %s) are standard according to SDPX license list: %s"
                % (len(license_standard_list), license_num, license_standard_list)
            )
        else:
            msg = (
                "None of the license/s defined are standard according to SPDX license list: %s"
                % license_list
            )
        msg = " ".join([msg, "(points: %s)" % points])
        logger.info(msg)

        return (points, [{"message": msg, "points": points}])

    @ConfigTerms(term_id="terms_license")
    def rda_r1_1_03m(self, **kwargs):
        """Indicator R1.1-03M: Metadata refers to a machine-understandable reuse
        license.

        This indicator is linked to the following principle: R1.1: (Meta)data are released with a clear
        and accessible data usage license.

        This indicator is about the way that the reuse licence is expressed. Rather than being a human-readable text, the licence should be expressed in such a way that it can be processed by machines, without human intervention, for example in automated searches.

        Returns
        -------
        points
            100/100 if the license is provided in such a way that is machine understandable
        msg
            Message with the results or recommendations to improve this indicator
        """
        license_list = kwargs["License"]

        _points_license, _msg_license = self.rda_r1_1_02m(
            license_list=license_list, machine_readable=True
        )
        if _points_license == 100:
            _msg = "License/s are machine readable according to SPDX"
        elif _points_license == 0:
            _msg = "License/s are not machine readable according to SPDX"
        else:
            _msg = "A subset of the license/s are machine readable according to SPDX"
        logger.info(_msg)

        return (_points_license, [{"message": _msg, "points": _points_license}])
    
    @ConfigTerms(term_id="terms_provenance")
    def rda_r1_2_01m(self, **kwargs):
        """Indicator R1.2-01M: Metadata includes provenance information about community-
        specific standard.

        This indicator is linked to the following principle: R1.2: (Meta)data are associated with detailed provenance.

        This indicator requires the metadata to include information about the provenance of the data, i.e. information about the origin, history or workflow that generated the data, in a way that is compliant with the standards that are used in the community for which the data is curated.

        Implementation accorfding to what it is suggested in RDA documenation:
          - FAIRsharing lists standards form provenance.
          - According to PAV (Provenance Authoring and Versioning): https://pav-ontology.github.io/pav/, 
            I have adapted it to what we have in schema.org at the moment.
        
        Returns
        -------
        points
            100/100 if provenance information is provided
        msg
            Message with the results or recommendations to improve this indicator
        """
        msg_list = []
        points = 0

        term_data = kwargs["terms_provenance"]
        term_metadata = term_data["metadata"]

        msg_st_list = []
        for index, row in term_metadata.iterrows():
            msg_st_list.append(
                _("Metadata found for provenance") + ": " + row["element"]
            )
            logging.debug(_("Metadata found for provenance") + ": " + row["element"])

        if msg_st_list:
            points = 100
            msg_st_list = set(msg_st_list)
            msg_list.append({"message": ", ".join(msg_st_list), "points": points})
        else:
            points = 0
            msg_list.append(
                {
                    "message": _("No metadata for provenance found"),
                    "points": points,
                }
            )

        return (points, msg_list)

    def rda_r1_2_02m(self):
        """Indicator RDA-A1-01M
        This indicator is linked to the following principle: R1.2: (Meta)data are associated with
        detailed provenance. More information about that principle can be found here.
        This indicator requires that the metadata provides provenance information according to a
        cross-domain language.
        Technical proposal:
        Parameters
        ----------
        item_id : str
            Digital Object identifier, which can be a generic one (DOI, PID), or an internal (e.g. an
            identifier from the repo)
        Returns
        -------
        points
            A number between 0 and 100 to indicate how well this indicator is supported
        msg
            Message with the results or recommendations to improve this indicator
        """
        points = 0
        msg = [
            {
                "message": _("No metadata provenance information expressed in a cross-domain language."),
                "points": points,
            }
        ]
        return (points, msg)
    
    def rda_r1_3_01d(self, **kwargs):
        """Indicator RDA-R1.3-01D: Data complies with a community standard.

        This indicator is linked to the following principle: R1.3: (Meta)data meet domain-relevant
        community standards.

        This indicator requires that data complies with community standards.

        Returns
        --------
        points
           100/100 if the data standard appears in Fairsharing (0/100 otherwise)
        """
        (_points, _msg) = self.rda_i1_01d()

        return (_points, [{"message": _msg, "points": _points}])




    
    