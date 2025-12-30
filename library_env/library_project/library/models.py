from django.db import models

# Create your models here.
class author(models.Model):
    first_name = models.CharField("prénom", max_length=50)
    last_name = models.CharField("nom", max_length=50)
    birth_date = models.DateField("Date de naissance")
    nationality = models.CharField("nationalité", max_length=50)
    bio = models.TextField("Biographie", blank=True)
    death_date = models.DateField("Date de décès", null=True, blank=True)
    website = models.URLField("Site web", blank=True)
    photo = models.ImageField("Photo", upload_to='authors/', null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['first_name', 'last_name', 'birth_date'], name='unique_author')
        ]
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    def delete(self, *args, **kwargs):
        if self.books.exists():
            raise ValidationError("Impossible de supprimer un auteur ayant des livres associés.")
        return super().delete(*args, **kwargs)
    
class Category(models.Model):
    name = models.CharField("Nom", max_length=120, unique=True)
    description = models.TextField("Description", blank=True)
    image = models.ImageField("Image", upload_to='categories/', null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name        

class Book(models.Model):
    LANGUAGE_CHOICES = [
        ('FR', 'Français'),
        ('EN', 'Anglais'),
        ('ES', 'Espagnol'),
        ('DE', 'Allemand'),
        ('IT', 'Italien'),
        ('OTHER', 'Autre'),
    ]

    ISBN = models.CharField(max_length=13, unique=True)
    count_available = models.PositiveIntegerField(default=1)
    count_total = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    author = models.ForeignKey(author, on_delete=models.CASCADE, related_name='books', verbose_name="Auteur")
    published_date = models.DateField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='books', verbose_name="Catégorie", null=True, blank=True)
    description = models.TextField("Description", blank=True)
    language = models.CharField("Langue", max_length=10, choices=LANGUAGE_CHOICES, default="fr")
    pages = models.PositiveIntegerField("Pages", null=True, blank=True)
    publisher = models.CharField("Maison d'édition", max_length=150, blank=True)
    cover = models.ImageField("Couverture", upload_to="covers/", blank=True, null=True)
    created_at = models.DateTimeField("Ajouté le", auto_now_add=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["isbn"]),
            models.Index(fields=["publication_year"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.available_copies > self.total_copies:
            raise ValidationError({"available_copies": "Les exemplaires disponibles ne peuvent pas dépasser le total."})

    def has_active_loans(self):
        return self.loans.filter(status=Loan.Status.ACTIVE).exists()

    def delete(self, *args, **kwargs):
        if self.has_active_loans():
            raise ValidationError("Impossible de supprimer ce livre : des emprunts sont actifs.")
        return super().delete(*args, **kwargs)

    # Méthodes métier (Phase 7)
    def is_available(self):
        return self.available_copies > 0

    def decrement_available(self, qty=1):
        if qty < 1:
            return
        if self.available_copies < qty:
            raise ValidationError("Pas assez d'exemplaires disponibles.")
        self.available_copies -= qty
        self.save(update_fields=["available_copies"])

    def increment_available(self, qty=1):
        if qty < 1:
            return
        if self.available_copies + qty > self.total_copies:
            self.available_copies = self.total_copies
        else:
            self.available_copies += qty
        self.save(update_fields=["available_copies"])

    def active_loans(self):
        return self.loans.filter(status=Loan.Status.ACTIVE)

    def occupancy_rate(self):
        # empruntés / total
        borrowed = self.total_copies - self.available_copies
        if self.total_copies == 0:
            return 0
        return round((borrowed / self.total_copies) * 100, 2)


class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        RETURNED = "returned", "Retourné"
        OVERDUE = "overdue", "En retard"

    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name="loans",
        verbose_name="Livre",
    )
    borrower_full_name = models.CharField("Nom complet", max_length=150)
    borrower_email = models.EmailField("Email")
    card_number = models.CharField("N° carte", max_length=30)

    loaned_at = models.DateTimeField("Emprunté le", default=timezone.now)
    due_at = models.DateTimeField("Date limite", blank=True, null=True)
    returned_at = models.DateTimeField("Retourné le", blank=True, null=True)

    status = models.CharField("Statut", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    librarian_notes = models.TextField("Commentaires", blank=True)

    class Meta:
        ordering = ["-loaned_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["card_number"]),
            models.Index(fields=["borrower_email"]),
        ]

    def __str__(self):
        return f"{self.book.title} — {self.borrower_full_name}"

    # Règles métier (Phase 7)
    @property
    def is_overdue(self):
        return self.status == self.Status.OVERDUE or (self.returned_at is None and self.due_at and timezone.now() > self.due_at)

    def late_days(self):
        end = self.returned_at or timezone.now()
        if not self.due_at or end <= self.due_at:
            return 0
        delta = end.date() - self.due_at.date()
        return max(delta.days, 0)

    def penalty_amount(self):
        # Exemple : 0,50€ / jour de retard (tu peux ajuster)
        return round(self.late_days() * 0.5, 2)

    def mark_returned(self):
        if self.status == self.Status.RETURNED:
            return
        self.returned_at = timezone.now()
        self.status = self.Status.RETURNED
        self.save(update_fields=["returned_at", "status"])

    def extend(self, days=7):
        if not self.due_at:
            return
        self.due_at = self.due_at + timezone.timedelta(days=days)
        self.save(update_fields=["due_at"])