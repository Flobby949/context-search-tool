package access;

public final class WhitelistValidation {
    public boolean validateAccess(String subject) {
        return subject != null && !subject.isBlank();
    }
}
