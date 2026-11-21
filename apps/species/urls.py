from django.urls import path

from .views import (
    SpecieDetailView,
    SpecieFeedingReferenceDetailView,
    SpecieFeedingReferenceListCreateView,
    SpecieListCreateView,
    SpecieParameterDetailView,
    SpecieParameterListCreateView,
    SpeciePondTypeDetailView,
    SpeciePondTypeListCreateView,
    SpecieProductionReferenceDetailView,
    SpecieProductionReferenceListCreateView,
)

urlpatterns = [
    path("species/", SpecieListCreateView.as_view()),
    path("species/<int:specie_id>/", SpecieDetailView.as_view()),
    path("species/<int:specie_id>/pond-types/", SpeciePondTypeListCreateView.as_view()),
    path("species/<int:specie_id>/pond-types/<int:pond_type_id>/", SpeciePondTypeDetailView.as_view()),
    path("species/<int:specie_id>/parameters/", SpecieParameterListCreateView.as_view()),
    path("species/<int:specie_id>/parameters/<int:parameter_id>/", SpecieParameterDetailView.as_view()),
    path("species/<int:specie_id>/feeding-references/", SpecieFeedingReferenceListCreateView.as_view()),
    path("species/<int:specie_id>/feeding-references/<int:ref_id>/", SpecieFeedingReferenceDetailView.as_view()),
    path("species/<int:specie_id>/production-references/", SpecieProductionReferenceListCreateView.as_view()),
    path("species/<int:specie_id>/production-references/<int:ref_id>/", SpecieProductionReferenceDetailView.as_view()),
]
