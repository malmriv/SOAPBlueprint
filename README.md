# SOAP Blueprint

[This tool](https://soapblueprint.streamlit.app) allows API devs to build WSDL files to define your SOAP service schema. Validated for SAP services (ECC, S/4HANA, Integration Suite) as well as MuleSoft.

![A screenshot of the app](https://github.com/malmriv/malmriv.github.io/blob/master/_posts/images/soapblueprint-view-tool.png?raw=true)

Features:

- Define request & response structure (with names, datatypes, cardinality & arbitrarily deep nesting).
- Generate WSDL as well as standalone XSD automatically.
- Generate a valid SOAP request body that fits your schema.
- Generate a Postman collection that contains your request, adequate POST method & adequate Content-Type header.

## Why

Those who work with SOAP APIs (a.k.a. webservices) know that it can be difficult to generate a service definition that works for all parties involved. There can be problems with several components:

 - Namespaces.
 - [Nesting styles](https://www.oracle.com/technical-resources/articles/java/design-patterns.html) in the field schema (Matrioshka, Venetian blinds, Salami slices...)
 - Binding definition.
 - Security policies.
 - Etc.

For this reason, it is useful to adhere to a format that is known to work, but even then the XSD can be difficult to maintain when the structures are very nested. Therefore, having a *dev-friendly* generator seems like a good idea to me. Initially, I decided to write it in R, using [Shiny](https://shiny.posit.co) for the UI. That version worked but had two important limitations:

  1. It **only supported one level of field nesting** (a parent could have children, but children could not have children of their own). This was due to me having implemented a nesting system that proved too hard to generalise for more than one depth. Furthermore, Shiny's reactive model itself made it difficult to manage the kind of recursive, deeply nested data structures I had in mind.
  2. The codebase **was a single monolithic file mixing UI & core logic**, as often happens with Shiny apps. This is my fault, though. I just could not be bothered to refactor the code, which started as a personal project and ended up being used by my colleagues.
  
Both reasons made it very hard for me to maintain the app when the need to add new features came up. This is an improved version of that tool. I have chosen an approach that [I have used in the past](https://github.com/malmriv/integration-suite-explorer) with good results: Python for the core logic and Streamlit for the UI. More details about this [on my blog]().

## New stuff!

Some things I am quite happy about:

- Arbitrarily deep nesting (finally!). Fields can contain fields to any depth. The data model is a recursive tree, and the WSDL generation walks it accordingly.
- A standalone XSD is generated and made available for download.
- A Sample SOAP message is generated for the request, and another for the response. Both the Envelope expected by SAP services and the correct namespace handling are included.
- A Postman collection is also made available for download. Postman is notoriously bad at converting WSDLs into working collections, and I tried to cover this gap by generating a Postman file with the correct adaptations: POST method for request, correct Content-Type (Postman insists on setting it to application/xml, which is not always accepted), correct namespace handling & an Envelope included by default in the request.
- Proper XML construction using lxml instead of string concatenation. This results in fewer risks of mismatched nodes.
- Field types are drawn from the [W3C XSD built-in datatypes](https://www.w3.org/TR/xmlschema-2/#d0e11239) specification (string, int, decimal, date, boolean, and others). Not all are used, because I honestly cannot for the life of me understand their use cases. The ones I included seem more than enough, but I am open to change requests.
- Configurable service metadata: service name, namespace, and request/response element names.
- Clean separation between core logic (`core/`) and UI (`app/`). The core module has no Streamlit dependency and could be used from a CLI or API (to be continued...)
- Test suite covering flat fields, nested fields, deep nesting (3+ levels), arrays (unbounded), and input validation.
- The Streamlit server does not shut down automatically after a few minutes of continued use. (The fact that Shiny's free plan server does wind down after a few minutes drove me nuts, because it meant starting over).

## Structure

```
core/
  models.py        Field and ServiceConfig dataclasses
  builder.py       Field tree to WSDL (lxml)
  validators.py    XML name and type validation
app/
  streamlit_app.py UI
tests/
  test_builder.py
graphics/         Blobs used in the UI
  header-image.png
```

## Running locally

```
pip install streamlit lxml
python -m streamlit run app/streamlit_app.py
```

## Tests

```
pip install pytest lxml
python -m pytest tests/
```
