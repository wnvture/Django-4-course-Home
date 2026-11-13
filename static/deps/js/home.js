"use strict";
// Optional presentation only; checkout and cart mutations also work without JavaScript.
const checkout = document.getElementById("checkout-form");
if (checkout) {
  const address = checkout.querySelector("[data-delivery-address]");
  const updateAddress = () => {
    const selected = checkout.querySelector('input[name="requires_delivery"]:checked');
    if (address && selected) address.hidden = selected.value !== "1";
  };
  checkout.querySelectorAll('input[name="requires_delivery"]').forEach(input => input.addEventListener("change", updateAddress));
  updateAddress();
}
